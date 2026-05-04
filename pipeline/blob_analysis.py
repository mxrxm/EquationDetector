"""
blob_analysis.py  [v3]
================
Stage 3, 4 & 5 of the Equation Detector Pipeline.

Pure Python — no external dependencies.

Change log
----------
v3 (current)
    Stage 4 — estimate_font_size():
        • fill_ratio >= 0.25 filter — hollow math symbols (integrals,
          summations, large brackets) have low fill_ratio and were
          accumulating area-weight that shifted the peak away from body text
    Stage 5 — group_blobs_into_regions():
        • para_v_px capped at font_size * 4.0 — prevents valley detector
          from merging across display-equation or heading gaps
        • min_region_density raised from 0.03 → 0.05

v2
    Stage 3: deque BFS, fill_ratio, max_blob_area_ratio filter
    Stage 4: right_margin_crop, MIN_AREA, area-weighted histogram, 3-bin smooth
    Stage 5: two-pass Union-Find, auto para_v_px, height/aspect/density guards
"""

from collections import deque

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — Connected Component Analysis (BFS, 8-connected)
# ═══════════════════════════════════════════════════════════════════════════════

# def find_all_blobs(binary, min_blob_area=5, max_blob_area_ratio=0.05):
#     h, w         = len(binary), len(binary[0])
#     img_area     = h * w
#     max_box_area = img_area * max_blob_area_ratio
#     visited      = [[False] * w for _ in range(h)]
#     blobs        = []

#     NEIGHBOURS = [(-1,-1),(-1,0),(-1,1),
#                   ( 0,-1),       ( 0,1),
#                   ( 1,-1),( 1,0),( 1,1)]

#     def bfs(start_r, start_c):
#         queue = deque()
#         queue.append((start_r, start_c))
#         visited[start_r][start_c] = True
#         area = 0
#         y1 = y2 = start_r
#         x1 = x2 = start_c
#         while queue:
#             r, c = queue.popleft()
#             area += 1
#             if r < y1: y1 = r
#             if r > y2: y2 = r
#             if c < x1: x1 = c
#             if c > x2: x2 = c
#             for dr, dc in NEIGHBOURS:
#                 nr, nc = r + dr, c + dc
#                 if (0 <= nr < h and 0 <= nc < w
#                         and not visited[nr][nc]
#                         and binary[nr][nc] == 1):
#                     visited[nr][nc] = True
#                     queue.append((nr, nc))
#         return area, y1, y2, x1, x2

#     for r in range(h):
#         for c in range(w):
#             if binary[r][c] == 1 and not visited[r][c]:
#                 area, y1, y2, x1, x2 = bfs(r, c)
#                 if area < min_blob_area:
#                     continue
#                 bh = y2 - y1 + 1
#                 bw = x2 - x1 + 1
#                 box_area = bh * bw
#                 if box_area > max_box_area:
#                     continue
#                 blobs.append({
#                     "x1":           x1,
#                     "y1":           y1,
#                     "x2":           x2,
#                     "y2":           y2,
#                     "height":       bh,
#                     "width":        bw,
#                     "area":         area,
#                     "fill_ratio":   area / box_area if box_area > 0 else 0.0,
#                     "aspect_ratio": bw / bh if bh > 0 else 0.0,
#                     "center_r":     (y1 + y2) / 2.0,
#                     "center_c":     (x1 + x2) / 2.0,
#                 })
#     return blobs
def find_all_blobs(binary, min_blob_area=5):
    h, w    = len(binary), len(binary[0])
    visited = [[False] * w for _ in range(h)]
    blobs   = []

    def bfs(start_r, start_c):
        queue   = [(start_r, start_c)]
        visited[start_r][start_c] = True
        pixels  = []
        while queue:
            r, c = queue.pop(0)
            pixels.append((r, c))
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = r + dr, c + dc
                    if (0 <= nr < h and 0 <= nc < w
                            and not visited[nr][nc]
                            and binary[nr][nc] == 1):
                        visited[nr][nc] = True
                        queue.append((nr, nc))
        return pixels

    for r in range(h):
        for c in range(w):
            if binary[r][c] == 1 and not visited[r][c]:
                pixels = bfs(r, c)
                if len(pixels) < min_blob_area:
                    continue
                rows = [p[0] for p in pixels]
                cols = [p[1] for p in pixels]
                y1, y2 = min(rows), max(rows)
                x1, x2 = min(cols), max(cols)
                bh = y2 - y1 + 1
                bw = x2 - x1 + 1
                blobs.append({
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "height":       bh,
                    "width":        bw,
                    "area":         len(pixels),
                    "aspect_ratio": bw / bh if bh > 0 else 0,
                    "center_r":     (y1 + y2) / 2,
                    "center_c":     (x1 + x2) / 2,
                })

    print(f"  Total blobs found: {len(blobs)}")
    return blobs


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 4 — Font size estimation
# ═══════════════════════════════════════════════════════════════════════════════

# def estimate_font_size(blobs, right_margin_crop=0.85):
#     """
#     Estimate dominant body-text glyph height via area-weighted histogram.

#     Filters applied before histogram:
#         aspect_ratio >= 0.4   — excludes tall-thin math symbols (integrals)
#         area         >= 20    — excludes micro noise fragments
#         fill_ratio   >= 0.25  — excludes hollow symbols (summation, brackets)
#                                 [FIX v3: this was the main cause of font_size=12]
#     Sidebar blobs (x > 85% image width) cropped before filtering.
#     """
#     if not blobs:
#         return 20

#     # Step 0: crop sidebar
#     img_width = max(b["x2"] for b in blobs)
#     x_limit   = img_width * right_margin_crop
#     blobs     = [b for b in blobs if b["center_c"] <= x_limit]
#     if not blobs:
#         return 20

#     # Step 1: filter
#     MIN_HEIGHT = 4
#     MIN_ASPECT = 0.4
#     MIN_AREA   = 20
#     MIN_FILL   = 0.25   # v3 fix — hollow symbols excluded

#     candidates = [b for b in blobs
#                   if b["height"]       >= MIN_HEIGHT
#                   and b["aspect_ratio"] >= MIN_ASPECT
#                   and b["area"]         >= MIN_AREA
#                   and b["fill_ratio"]   >= MIN_FILL]

#     # graceful fallbacks
#     if not candidates:
#         candidates = [b for b in blobs
#                       if b["height"] >= MIN_HEIGHT
#                       and b["aspect_ratio"] >= MIN_ASPECT
#                       and b["area"] >= MIN_AREA]
#     if not candidates:
#         candidates = blobs

#     # Step 2: area-weighted histogram
#     hist = {}
#     for b in candidates:
#         h = b["height"]
#         hist[h] = hist.get(h, 0) + b["area"]

#     # Step 3: find all local peaks in the smoothed histogram
#     # then return the HIGHEST-HEIGHT significant peak.
#     #
#     # Why: math-heavy documents produce a bimodal distribution —
#     #   peak 1 at h~12  (inline equation symbols, subscripts)
#     #   peak 2 at h~16  (body text glyphs)
#     # The lower peak often has more total area in math articles.
#     # Picking the global maximum gives h=12; we want h=16.
#     # "Significant" = peak weight >= 30% of the strongest peak weight.
#     # Taking the highest-h significant peak gives body-text height.
#     peaks = []
#     for h in sorted(hist.keys()):
#         score = hist.get(h-1, 0) + hist.get(h, 0) + hist.get(h+1, 0)
#         left  = hist.get(h-2, 0) + hist.get(h-1, 0)
#         right = hist.get(h+1, 0) + hist.get(h+2, 0)
#         if score > left and score > right:
#             peaks.append((h, score))

#     if not peaks:
#         # degenerate: histogram has no local peak (flat or single bin)
#         best_h = max(hist, key=lambda h: hist[h])
#     else:
#         max_weight = max(s for _, s in peaks)
#         threshold  = max_weight * 0.30
#         sig_peaks  = [h for h, s in peaks if s >= threshold]
#         best_h     = max(sig_peaks)   # highest-h significant peak = body text

#     # Step 4: sanity clamp
#     return max(6, min(best_h, 120))
def estimate_font_size(blobs):
    if not blobs:
        return 20
    hist = {}
    for b in blobs:
        hist[b["height"]] = hist.get(b["height"], 0) + 1
    font_size = max(hist, key=hist.get)
    print(f"  Estimated font size: {font_size}px")
    return font_size


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 5 helpers
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
    Estimate the vertical gap threshold that separates adjacent lines
    within a paragraph from the larger gaps between paragraphs.

    Strategy
    --------
    Valley detection on a histogram requires dense data (many gaps).
    Most documents yield only 15-60 inter-line gaps after Pass 1 — far
    too sparse for reliable valley detection.

    Instead we use a percentile split:
    1. Collect all positive inter-line gaps between adjacent line regions.
    2. Sort them.
    3. Use the gap at the 40th percentile as the "typical line spacing".
    4. Return 1.5 × that value as the merge threshold.
       - Gaps <= threshold  → same paragraph  → merge
       - Gaps >  threshold  → different block → keep separate

    This is robust to sparse distributions because it doesn't require
    finding a histogram valley — it just needs the lower half of gaps
    to be smaller than the upper half, which is almost always true.

    Falls back to font_size * 2.5 if fewer than 3 gaps are available.
    Hard floor: result is always >= font_size * 1.5 (never merge too tightly).
    Hard ceiling applied by caller: font_size * 4.0.
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

    # Strategy: find the first significant jump in the sorted gap list.
    # Within a logical block (equation lines, tight prose) gaps are small
    # (< font_size). Between blocks gaps jump to font_size or larger.
    # We want to cut just BELOW that first big jump.
    #
    # Algorithm:
    # 1. Walk sorted gaps; look for the first gap value that is both
    #    >= font_size AND at least 1.5× the previous gap value (a jump).
    # 2. The threshold is set just below that jump value.
    # 3. If no clear jump is found, fall back to the minimum gap that
    #    is >= font_size (i.e. merge only truly tight lines).
    # 4. Hard floor: font_size * 1.1 (always separate lines of different size).
    # 5. Hard ceiling applied by caller: font_size * 4.0.

    # Find first jump at or above font_size
    threshold = None
    for i in range(1, n):
        if gaps[i] >= font_size and gaps[i] > gaps[i-1] * 1.5:
            # cut just below this jump: use previous gap + small margin
            threshold = gaps[i-1] + 2
            break

    if threshold is None:
        # No clear jump — use the first gap >= font_size as the cut
        above = [g for g in gaps if g >= font_size]
        if above:
            threshold = above[0] - 1
        else:
            threshold = font_size * 1.1

    # Hard floor
    threshold = max(threshold, font_size * 1.1)

    return float(threshold)


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
        rx1 = min(b["x1"] for b in col); ry1 = min(b["y1"] for b in col)
        rx2 = max(b["x2"] for b in col); ry2 = max(b["y2"] for b in col)
        rw = rx2 - rx1 + 1; rh = ry2 - ry1 + 1
        box_area = rw * rh
        density  = sum(b["area"] for b in col) / box_area if box_area > 0 else 0.0
        if density < min_region_density:
            continue
        result.append({"x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2,
                        "width": rw, "height": rh, "blobs": col,
                        "blob_count": len(col), "density": density})
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
        rx1 = min(b["x1"] for b in strip); ry1 = min(b["y1"] for b in strip)
        rx2 = max(b["x2"] for b in strip); ry2 = max(b["y2"] for b in strip)
        rw = rx2 - rx1 + 1; rh = ry2 - ry1 + 1
        box_area = rw * rh
        density  = sum(b["area"] for b in strip) / box_area if box_area > 0 else 0.0
        n_lines  = max(1, rh / font_size)
        if density < min_region_density / (n_lines ** 0.5):
            continue
        result.append({"x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2,
                        "width": rw, "height": rh, "blobs": strip,
                        "blob_count": len(strip), "density": density})
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 5 — Group blobs into regions  (two-pass Union-Find)
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def run_blob_analysis(binary, min_blob_area=5):
    """
    Run the full blob analysis pipeline on a binarized image.

    Parameters
    ----------
    binary               : 2-D list[list[int]]  from preprocessing.preprocess()
    min_blob_area        : int    minimum ink pixels to keep a blob
    max_blob_area_ratio  : float  blobs whose box > this fraction of image
                                  area are discarded (photos, figures)
    min_blobs_per_region : int    minimum blobs to keep a region

    Returns
    -------
    dict:  blobs, font_size, regions
    """
    blobs     = find_all_blobs(binary,
                               min_blob_area=min_blob_area)
    font_size = estimate_font_size(blobs)

    return {"blobs": blobs, "font_size": font_size}
