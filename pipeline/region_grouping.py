# """
# region_grouping.py — Group blobs into candidate regions.

# Two-pass strategy
# -----------------
# Pass A (tight)  — connect blobs that are within one line-spacing.
#                   Produces small line-level regions.
# Pass B (para)   — merge line regions whose vertical gap is below the
#                   auto-detected paragraph gap threshold.

# Post-processing — split any surviving region that is too wide
#                   (column split) or too tall (strip split).
# """


# # ═══════════════════════════════════════════════════════════════════════════════
# # Internal helpers
# # ═══════════════════════════════════════════════════════════════════════════════

# def _union_find_group(blobs, h_gap, v_gap, min_members=1):
#     """Union-Find proximity grouping with path compression + v_gap early-break."""
#     sorted_blobs = sorted(blobs, key=lambda b: (b["y1"], b["x1"]))
#     n      = len(sorted_blobs)
#     parent = list(range(n))

#     def find(i):
#         while parent[i] != i:
#             parent[i] = parent[parent[i]]
#             i = parent[i]
#         return i

#     def union(i, j):
#         parent[find(i)] = find(j)

#     for i in range(n):
#         bi = sorted_blobs[i]
#         for j in range(i + 1, n):
#             bj = sorted_blobs[j]
#             if bj["y1"] - bi["y2"] > v_gap:
#                 break
#             v_dist = max(0, bj["y1"] - bi["y2"])
#             h_dist = max(0, max(bi["x1"], bj["x1"]) - min(bi["x2"], bj["x2"]))
#             if v_dist <= v_gap and h_dist <= h_gap:
#                 union(i, j)

#     groups = {}
#     for i in range(n):
#         groups.setdefault(find(i), []).append(sorted_blobs[i])

#     regions = []
#     for members in groups.values():
#         if len(members) < min_members:
#             continue
#         rx1 = min(b["x1"] for b in members)
#         ry1 = min(b["y1"] for b in members)
#         rx2 = max(b["x2"] for b in members)
#         ry2 = max(b["y2"] for b in members)
#         rw  = rx2 - rx1 + 1
#         rh  = ry2 - ry1 + 1
#         box_area = rw * rh
#         ink_area = sum(b["area"] for b in members)
#         regions.append({
#             "x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2,
#             "width": rw, "height": rh,
#             "blob_count": len(members),
#             "density": ink_area / box_area if box_area > 0 else 0.0,
#             "blobs": members,
#         })
#     return regions


# def _estimate_para_gap_factor(line_regions, font_size):
#     """
#     Auto-detect the vertical gap threshold that separates lines within
#     a paragraph from gaps between paragraphs/blocks.

#     Finds the first significant jump in the sorted inter-line gap list
#     at or above font_size, and cuts just below it.
#     Falls back to font_size * 2.5 if fewer than 3 gaps are available.
#     Hard floor: font_size * 1.1.
#     """
#     if len(line_regions) < 3:
#         return font_size * 2.5

#     sorted_lines = sorted(line_regions, key=lambda r: r["y1"])
#     gaps = []
#     for i in range(len(sorted_lines) - 1):
#         gap = sorted_lines[i + 1]["y1"] - sorted_lines[i]["y2"]
#         if gap > 0:
#             gaps.append(gap)

#     if len(gaps) < 3:
#         return font_size * 2.5

#     gaps.sort()
#     n = len(gaps)

#     threshold = None
#     for i in range(1, n):
#         if gaps[i] >= font_size and gaps[i] > gaps[i - 1] * 1.5:
#             threshold = gaps[i - 1] + 2
#             break

#     if threshold is None:
#         above = [g for g in gaps if g >= font_size]
#         if above:
#             threshold = above[0] - 1
#         else:
#             threshold = font_size * 1.1

#     return float(max(threshold, font_size * 1.1))


# def _split_region_by_x_gap(group_blobs, font_size, h_gap_factor,
#                              min_blobs_per_region, min_region_density):
#     """Split a too-wide region into x-axis columns."""
#     h_gap       = font_size * h_gap_factor
#     sorted_by_x = sorted(group_blobs, key=lambda b: b["center_c"])
#     columns, current = [], [sorted_by_x[0]]
#     for b in sorted_by_x[1:]:
#         if b["x1"] - current[-1]["x2"] > h_gap:
#             columns.append(current)
#             current = [b]
#         else:
#             current.append(b)
#     columns.append(current)

#     result = []
#     for col in columns:
#         if len(col) < min_blobs_per_region:
#             continue
#         rx1 = min(b["x1"] for b in col)
#         ry1 = min(b["y1"] for b in col)
#         rx2 = max(b["x2"] for b in col)
#         ry2 = max(b["y2"] for b in col)
#         rw  = rx2 - rx1 + 1
#         rh  = ry2 - ry1 + 1
#         box_area = rw * rh
#         density  = sum(b["area"] for b in col) / box_area if box_area > 0 else 0.0
#         if density < min_region_density:
#             continue
#         result.append({
#             "x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2,
#             "width": rw, "height": rh,
#             "blobs": col,
#             "blob_count": len(col),
#             "density": density,
#         })
#     return result


# def _split_region_by_y_gap(group_blobs, font_size, line_v_factor,
#                              min_blobs_per_region, min_region_density):
#     """Split a too-tall region into horizontal strips."""
#     v_cut  = font_size * line_v_factor * 1.5
#     by_y   = sorted(group_blobs, key=lambda b: b["center_r"])
#     strips, current = [], [by_y[0]]
#     for b in by_y[1:]:
#         if b["y1"] - current[-1]["y2"] > v_cut:
#             strips.append(current)
#             current = [b]
#         else:
#             current.append(b)
#     strips.append(current)

#     result = []
#     for strip in strips:
#         if len(strip) < min_blobs_per_region:
#             continue
#         rx1 = min(b["x1"] for b in strip)
#         ry1 = min(b["y1"] for b in strip)
#         rx2 = max(b["x2"] for b in strip)
#         ry2 = max(b["y2"] for b in strip)
#         rw  = rx2 - rx1 + 1
#         rh  = ry2 - ry1 + 1
#         box_area = rw * rh
#         density  = sum(b["area"] for b in strip) / box_area if box_area > 0 else 0.0
#         n_lines  = max(1, rh / font_size)
#         if density < min_region_density / (n_lines ** 0.5):
#             continue
#         result.append({
#             "x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2,
#             "width": rw, "height": rh,
#             "blobs": strip,
#             "blob_count": len(strip),
#             "density": density,
#         })
#     return result


# # ═══════════════════════════════════════════════════════════════════════════════
# # PUBLIC ENTRY POINT
# # ═══════════════════════════════════════════════════════════════════════════════

# def group_blobs_into_regions(blobs, font_size,
#                               h_gap_factor=2.0,
#                               line_v_factor=1.5,
#                               para_v_factor=None,
#                               min_blobs_per_region=2,
#                               max_region_aspect=25.0,
#                               max_region_height_factor=20.0,
#                               min_region_density=0.02):
#     """
#     Group blobs into candidate regions using a two-pass strategy.

#     Parameters
#     ----------
#     blobs                   : list[dict]  from find_all_blobs()
#     font_size               : int         estimated body-text height in px
#     h_gap_factor            : float       horizontal gap in font_size units (default 2.0)
#     line_v_factor           : float       Pass A vertical gap — within-line merge (default 1.2)
#     para_v_factor           : float|None  Pass B vertical gap — paragraph merge.
#                                           If None, auto-detected from Pass A output.
#     min_blobs_per_region    : int         minimum blobs to keep a region (default 2)
#     max_region_aspect       : float       width/height above which column-split fires (default 25)
#     max_region_height_factor: float       height/font_size above which strip-split fires (default 20)
#     min_region_density      : float       ink/box ratio below which region is dropped (default 0.02)

#     Returns
#     -------
#     list[dict] — each dict has:
#         x1, y1, x2, y2, width, height, blob_count, density, blobs
#     """
#     if not blobs:
#         return []

#     h_gap      = font_size * h_gap_factor
#     line_v_gap = font_size * line_v_factor

#     # ── Pass A: tight grouping — connect blobs within one line-spacing ────────
#     line_regions = _union_find_group(
#         blobs,
#         h_gap=h_gap,
#         v_gap=line_v_gap,
#         min_members=1
#     )

#     # ── Auto-detect paragraph gap if not supplied ─────────────────────────────
#     if para_v_factor is None:
#         para_v_px = _estimate_para_gap_factor(line_regions, font_size)
#         # Hard ceiling: never merge more than 4 line-heights apart
#         para_v_px = min(para_v_px, font_size * 4.0)
#     else:
#         para_v_px = font_size * para_v_factor

#     # ── Pass B: paragraph grouping — merge adjacent line regions ─────────────
#     # Treat each line_region's bounding box as a single "super-blob"
#     super_blobs = []
#     for lr in line_regions:
#         super_blobs.append({
#             "x1":      lr["x1"],
#             "y1":      lr["y1"],
#             "x2":      lr["x2"],
#             "y2":      lr["y2"],
#             "center_r": (lr["y1"] + lr["y2"]) / 2,
#             "center_c": (lr["x1"] + lr["x2"]) / 2,
#             "area":    lr["density"] * lr["width"] * lr["height"],
#             "_blobs":  lr["blobs"],   # carry original blobs through
#         })

#     para_regions_raw = _union_find_group(
#         super_blobs,
#         h_gap=h_gap,
#         v_gap=para_v_px,
#         min_members=1
#     )

#     # Rebuild real blob lists from merged super-blobs
#     para_regions = []
#     for pr in para_regions_raw:
#         real_blobs = []
#         for sb in pr["blobs"]:
#             real_blobs.extend(sb.get("_blobs", [sb]))
#         if len(real_blobs) < min_blobs_per_region:
#             continue

#         rx1 = min(b["x1"] for b in real_blobs)
#         ry1 = min(b["y1"] for b in real_blobs)
#         rx2 = max(b["x2"] for b in real_blobs)
#         ry2 = max(b["y2"] for b in real_blobs)
#         rw  = rx2 - rx1 + 1
#         rh  = ry2 - ry1 + 1
#         box_area = rw * rh
#         density  = sum(b["area"] for b in real_blobs) / box_area if box_area > 0 else 0.0

#         if density < min_region_density:
#             continue

#         para_regions.append({
#             "x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2,
#             "width": rw, "height": rh,
#             "blob_count": len(real_blobs),
#             "density": density,
#             "blobs": real_blobs,
#         })

#     # ── Post-processing: split oversized regions ──────────────────────────────
#     final = []
#     for region in para_regions:
#         rw = region["width"]
#         rh = region["height"]
#         ar = rw / rh if rh > 0 else 0

#         # Too wide → column split
#         if ar > max_region_aspect:
#             parts = _split_region_by_x_gap(
#                 region["blobs"], font_size, h_gap_factor,
#                 min_blobs_per_region, min_region_density
#             )
#             final.extend(parts)
#             continue

#         # Too tall → strip split
#         if rh > font_size * max_region_height_factor:
#             parts = _split_region_by_y_gap(
#                 region["blobs"], font_size, line_v_factor,
#                 min_blobs_per_region, min_region_density
#             )
#             final.extend(parts)
#             continue

#         final.append(region)

#     print(f"  Regions after grouping: {len(final)}  "
#           f"(pass_a={len(line_regions)}  para_v={para_v_px:.1f}px)")
#     return final
"""
region_grouping.py — Group blobs into candidate regions.

Two-pass strategy
-----------------
Pass A (tight)  — connect blobs that are within one line-spacing.
                  Produces small line-level regions.
Pass B (para)   — merge line regions whose vertical gap is below the
                  auto-detected paragraph gap threshold.
                  Uses a wider horizontal gap than Pass A, because
                  super-blobs (line bounding boxes) can be separated
                  by large whitespace (e.g. the rightmost term of a
                  display equation) that would never appear between
                  individual glyphs.

Post-processing — split any surviving region that is too wide
                  (column split) or too tall (strip split).
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _union_find_group(blobs, h_gap, v_gap, min_members=1):
    """Union-Find proximity grouping with path compression + v_gap early-break."""
    sorted_blobs = sorted(blobs, key=lambda b: (b["y1"], b["x1"]))
    n      = len(sorted_blobs)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    for i in range(n):
        bi = sorted_blobs[i]
        for j in range(i + 1, n):
            bj = sorted_blobs[j]
            if bj["y1"] - bi["y2"] > v_gap:
                break
            v_dist = max(0, bj["y1"] - bi["y2"])
            h_dist = max(0, max(bi["x1"], bj["x1"]) - min(bi["x2"], bj["x2"]))
            if v_dist <= v_gap and h_dist <= h_gap:
                union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(sorted_blobs[i])

    regions = []
    for members in groups.values():
        if len(members) < min_members:
            continue
        rx1 = min(b["x1"] for b in members)
        ry1 = min(b["y1"] for b in members)
        rx2 = max(b["x2"] for b in members)
        ry2 = max(b["y2"] for b in members)
        rw  = rx2 - rx1 + 1
        rh  = ry2 - ry1 + 1
        box_area = rw * rh
        ink_area = sum(b["area"] for b in members)
        regions.append({
            "x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2,
            "width": rw, "height": rh,
            "blob_count": len(members),
            "density": ink_area / box_area if box_area > 0 else 0.0,
            "blobs": members,
        })
    return regions


def _estimate_para_gap_factor(line_regions, font_size):
    """
    Auto-detect the vertical gap threshold that separates lines within
    a paragraph from gaps between paragraphs/blocks.

    Finds the first significant jump in the sorted inter-line gap list
    at or above font_size, and cuts just below it.
    Falls back to font_size * 2.5 if fewer than 3 gaps are available.
    Hard floor: font_size * 1.1.
    """
    if len(line_regions) < 3:
        return font_size * 2.5

    sorted_lines = sorted(line_regions, key=lambda r: r["y1"])
    gaps = []
    for i in range(len(sorted_lines) - 1):
        gap = sorted_lines[i + 1]["y1"] - sorted_lines[i]["y2"]
        if gap > 0:
            gaps.append(gap)

    if len(gaps) < 3:
        return font_size * 2.5

    gaps.sort()
    n = len(gaps)

    threshold = None
    for i in range(1, n):
        if gaps[i] >= font_size and gaps[i] > gaps[i - 1] * 1.5:
            threshold = gaps[i - 1] + 2
            break

    if threshold is None:
        above = [g for g in gaps if g >= font_size]
        if above:
            threshold = above[0] - 1
        else:
            threshold = font_size * 1.1

    return float(max(threshold, font_size * 1.1))


def _split_region_by_x_gap(group_blobs, font_size, h_gap_factor,
                             min_blobs_per_region, min_region_density):
    """Split a too-wide region into x-axis columns."""
    h_gap       = font_size * h_gap_factor
    sorted_by_x = sorted(group_blobs, key=lambda b: b["center_c"])
    columns, current = [], [sorted_by_x[0]]
    for b in sorted_by_x[1:]:
        if b["x1"] - current[-1]["x2"] > h_gap:
            columns.append(current)
            current = [b]
        else:
            current.append(b)
    columns.append(current)

    result = []
    for col in columns:
        if len(col) < min_blobs_per_region:
            continue
        rx1 = min(b["x1"] for b in col)
        ry1 = min(b["y1"] for b in col)
        rx2 = max(b["x2"] for b in col)
        ry2 = max(b["y2"] for b in col)
        rw  = rx2 - rx1 + 1
        rh  = ry2 - ry1 + 1
        box_area = rw * rh
        density  = sum(b["area"] for b in col) / box_area if box_area > 0 else 0.0
        if density < min_region_density:
            continue
        result.append({
            "x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2,
            "width": rw, "height": rh,
            "blobs": col,
            "blob_count": len(col),
            "density": density,
        })
    return result


def _split_region_by_y_gap(group_blobs, font_size, line_v_factor,
                             min_blobs_per_region, min_region_density):
    """Split a too-tall region into horizontal strips."""
    v_cut  = font_size * line_v_factor * 1.5
    by_y   = sorted(group_blobs, key=lambda b: b["center_r"])
    strips, current = [], [by_y[0]]
    for b in by_y[1:]:
        if b["y1"] - current[-1]["y2"] > v_cut:
            strips.append(current)
            current = [b]
        else:
            current.append(b)
    strips.append(current)

    result = []
    for strip in strips:
        if len(strip) < min_blobs_per_region:
            continue
        rx1 = min(b["x1"] for b in strip)
        ry1 = min(b["y1"] for b in strip)
        rx2 = max(b["x2"] for b in strip)
        ry2 = max(b["y2"] for b in strip)
        rw  = rx2 - rx1 + 1
        rh  = ry2 - ry1 + 1
        box_area = rw * rh
        density  = sum(b["area"] for b in strip) / box_area if box_area > 0 else 0.0
        n_lines  = max(1, rh / font_size)
        if density < min_region_density / (n_lines ** 0.5):
            continue
        result.append({
            "x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2,
            "width": rw, "height": rh,
            "blobs": strip,
            "blob_count": len(strip),
            "density": density,
        })
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def group_blobs_into_regions(blobs, font_size,
                              h_gap_factor=2.0,
                              line_v_factor=1.5,
                              para_v_factor=None,
                              min_blobs_per_region=2,
                              max_region_aspect=25.0,
                              max_region_height_factor=20.0,
                              min_region_density=0.02,
                              para_h_gap_factor=6.0):
    """
    Group blobs into candidate regions using a two-pass strategy.

    Parameters
    ----------
    blobs                   : list[dict]  from find_all_blobs()
    font_size               : int         estimated body-text height in px
    h_gap_factor            : float       Pass A horizontal gap in font_size units (default 2.0)
    line_v_factor           : float       Pass A vertical gap — within-line merge (default 1.5)
    para_v_factor           : float|None  Pass B vertical gap — paragraph merge.
                                          If None, auto-detected from Pass A output.
    min_blobs_per_region    : int         minimum blobs to keep a region (default 2)
    max_region_aspect       : float       width/height above which column-split fires (default 25)
    max_region_height_factor: float       height/font_size above which strip-split fires (default 20)
    min_region_density      : float       ink/box ratio below which region is dropped (default 0.02)
    para_h_gap_factor       : float       Pass B horizontal gap in font_size units (default 6.0).
                                          Wider than Pass A because super-blobs (line bounding
                                          boxes) can be separated by large whitespace — e.g. the
                                          rightmost term of a display equation — that would never
                                          appear between individual glyphs.

    Returns
    -------
    list[dict] — each dict has:
        x1, y1, x2, y2, width, height, blob_count, density, blobs
    """
    if not blobs:
        return []

    h_gap      = font_size * h_gap_factor
    line_v_gap = font_size * line_v_factor

    # ── Pass A: tight grouping — connect blobs within one line-spacing ────────
    line_regions = _union_find_group(
        blobs,
        h_gap=h_gap,
        v_gap=line_v_gap,
        min_members=1
    )

    # ── Auto-detect paragraph gap if not supplied ─────────────────────────────
    if para_v_factor is None:
        para_v_px = _estimate_para_gap_factor(line_regions, font_size)
        # Hard ceiling: never merge more than 4 line-heights apart
        para_v_px = min(para_v_px, font_size * 4.0)
    else:
        para_v_px = font_size * para_v_factor

    # ── Pass B: paragraph grouping — merge adjacent line regions ─────────────
    # Treat each line_region's bounding box as a single "super-blob".
    #
    # We need a wider horizontal gap than Pass A so that a display equation
    # whose rightmost term is separated by large whitespace (e.g. "φ(x⁽ⁱ⁾)"
    # after a long sum) gets merged back in.  But equation numbers like
    # "(25.4)" that sit on the far right margin must NOT be merged — they
    # inflate the bounding box and break downstream scoring.
    #
    # Solution: tag super-blobs that look like equation numbers and exclude
    # them from the wide-h_gap union step entirely.  They go through a
    # separate tight-h_gap pass so they can still merge with each other if
    # needed, but can never absorb an equation body.
    #
    # Equation-number super-blob criteria (ALL must hold):
    #   1. Very few source blobs  (≤ eq_num_blob_thresh)
    #   2. To its left there is a large gap relative to the page text width
    #      (≥ eq_gap_ratio of total text-column span)  AND  ≥ eq_gap_min_px
    #   3. Nothing to its right within the same horizontal band
    #      (i.e. it IS the rightmost super-blob on that row)

    para_h_gap     = font_size * para_h_gap_factor
    para_v_gap     = max(para_v_px, font_size * 2.0)

    eq_num_blob_thresh = max(4, int(font_size * 0.6))
    eq_gap_ratio       = 0.35   # left gap ≥ 35 % of text-column width
    eq_gap_min_px      = font_size * 3.0

    # Sort super-blobs left→right so we can inspect neighbours easily
    super_blobs = []
    for lr in line_regions:
        super_blobs.append({
            "x1":       lr["x1"],
            "y1":       lr["y1"],
            "x2":       lr["x2"],
            "y2":       lr["y2"],
            "center_r": (lr["y1"] + lr["y2"]) / 2,
            "center_c": (lr["x1"] + lr["x2"]) / 2,
            "area":     lr["density"] * lr["width"] * lr["height"],
            "_blobs":   lr["blobs"],
        })

    # Text-column span (used for gap-ratio denominator)
    if super_blobs:
        col_x1 = min(sb["x1"] for sb in super_blobs)
        col_x2 = max(sb["x2"] for sb in super_blobs)
        col_span = max(1, col_x2 - col_x1)
    else:
        col_span = 1

    def _is_eq_number(sb, all_sbs):
        """Return True if this super-blob looks like a margin equation number."""
        n_blobs = len(sb.get("_blobs", [sb]))
        if n_blobs > eq_num_blob_thresh:
            return False

        # Find super-blobs on the same row (vertically overlapping)
        row_mates = [
            s for s in all_sbs
            if s is not sb
            and s["y1"] < sb["y2"]
            and s["y2"] > sb["y1"]
        ]
        if not row_mates:
            return False  # isolated blob — don't tag as eq number

        # Must be the rightmost on its row
        if any(s["x1"] > sb["x1"] for s in row_mates):
            return False

        # Gap to nearest left row-mate
        left_mates = [s for s in row_mates if s["x2"] <= sb["x1"]]
        if not left_mates:
            return False
        nearest_left = max(left_mates, key=lambda s: s["x2"])
        left_gap = sb["x1"] - nearest_left["x2"]

        return (left_gap >= eq_gap_min_px
                and left_gap / col_span >= eq_gap_ratio)

    eq_num_indices = {
        i for i, sb in enumerate(super_blobs)
        if _is_eq_number(sb, super_blobs)
    }

    main_sbs  = [sb for i, sb in enumerate(super_blobs) if i not in eq_num_indices]
    eq_num_sbs = [sb for i, sb in enumerate(super_blobs) if i in eq_num_indices]

    # Wide-gap pass for main super-blobs (equation bodies merge freely)
    para_regions_raw = _union_find_group(
        main_sbs,
        h_gap=para_h_gap,
        v_gap=para_v_gap,
        min_members=1,
    )

    # Tight-gap pass for equation-number super-blobs (kept separate)
    if eq_num_sbs:
        eq_num_regions_raw = _union_find_group(
            eq_num_sbs,
            h_gap=h_gap,        # original tight gap — they won't absorb anything
            v_gap=para_v_gap,
            min_members=1,
        )
    else:
        eq_num_regions_raw = []

    all_raw = para_regions_raw + eq_num_regions_raw

    # Rebuild real blob lists from raw regions
    para_regions = []
    for pr in all_raw:
        real_blobs = []
        for sb in pr["blobs"]:
            real_blobs.extend(sb.get("_blobs", [sb]))

        if len(real_blobs) < min_blobs_per_region:
            continue

        rx1 = min(b["x1"] for b in real_blobs)
        ry1 = min(b["y1"] for b in real_blobs)
        rx2 = max(b["x2"] for b in real_blobs)
        ry2 = max(b["y2"] for b in real_blobs)
        rw  = rx2 - rx1 + 1
        rh  = ry2 - ry1 + 1
        box_area = rw * rh
        density  = sum(b["area"] for b in real_blobs) / box_area if box_area > 0 else 0.0

        if density < min_region_density:
            continue

        para_regions.append({
            "x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2,
            "width": rw, "height": rh,
            "blob_count": len(real_blobs),
            "density": density,
            "blobs": real_blobs,
        })

    # ── Post-processing: split oversized regions ──────────────────────────────
    final = []
    for region in para_regions:
        rw = region["width"]
        rh = region["height"]
        ar = rw / rh if rh > 0 else 0

        # Too wide → column split
        if ar > max_region_aspect:
            parts = _split_region_by_x_gap(
                region["blobs"], font_size, h_gap_factor,
                min_blobs_per_region, min_region_density
            )
            final.extend(parts)
            continue

        # Too tall → strip split
        if rh > font_size * max_region_height_factor:
            parts = _split_region_by_y_gap(
                region["blobs"], font_size, line_v_factor,
                min_blobs_per_region, min_region_density
            )
            final.extend(parts)
            continue

        final.append(region)

    print(f"  Regions after grouping: {len(final)}  "
          f"(pass_a={len(line_regions)}  para_v={para_v_px:.1f}px  "
          f"para_h={para_h_gap:.1f}px)")
    return final