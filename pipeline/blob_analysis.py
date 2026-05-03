"""
blob_analysis.py
================
Stage 3, 4 & 5 of the Equation Detector Pipeline.

Pure Python — no external dependencies.

Pipeline
--------
    3. find_all_blobs()           — CCA via BFS (8-connected), extract blob features
    4. estimate_font_size()       — modal blob height, giant-blob filtered + smoothed
    5. group_blobs_into_regions() — Union-Find proximity grouping

Public API
----------
    result = run_blob_analysis(binary, min_blob_area=5, min_blobs_per_region=2)

    result["blobs"]      — list of blob dicts  (see Blob schema below)
    result["font_size"]  — int   estimated body-text font height in pixels
    result["regions"]    — list of region dicts (see Region schema below)

Blob schema
-----------
    x1, y1, x2, y2     — bounding box (pixels)
    height, width       — bounding box dimensions
    area                — actual ink pixel count
    fill_ratio          — area / (width × height)   solidity: 1.0 = solid rect
    aspect_ratio        — width / height
    center_r, center_c  — centroid (row, col)

Region schema
-------------
    x1, y1, x2, y2     — bounding box enclosing all member blobs
    width, height       — bounding box dimensions
    blobs               — list of blob dicts inside this region
    blob_count          — len(blobs)
    density             — total ink area / region bounding-box area
"""

from collections import deque

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — Connected Component Analysis (BFS, 8-connected)
# ═══════════════════════════════════════════════════════════════════════════════

def find_all_blobs(binary, min_blob_area=5, max_blob_area_ratio=0.05):
    """
    Label every connected foreground component in `binary` and return
    a list of blob feature dicts.

    Parameters
    ----------
    binary              : 2-D list[list[int]]  0 = background, 1 = text/ink
    min_blob_area       : int    discard components with fewer ink pixels
    max_blob_area_ratio : float  discard blobs whose bounding box exceeds
                                 this fraction of the total image area
                                 (default 0.05 = 5%).
                                 Catches embedded photos, figures, large
                                 decorative elements that are not text.

    Returns
    -------
    list of blob dicts  (see module docstring for schema)

    Notes
    -----
    Enhancement over original:
    - deque + popleft()  replaces  list + pop(0)  → O(1) per step vs O(n)
    - fill_ratio added to each blob dict
    - bounding box tracked inside BFS (no post-pass min/max over pixel list)
    - max_blob_area_ratio filter removes embedded images / figures
    """
    h, w         = len(binary), len(binary[0])
    img_area     = h * w
    max_box_area = img_area * max_blob_area_ratio
    visited      = [[False] * w for _ in range(h)]
    blobs        = []

    # 8-connected neighbour offsets (same as original)
    NEIGHBOURS = [(-1,-1),(-1,0),(-1,1),
                  ( 0,-1),       ( 0,1),
                  ( 1,-1),( 1,0),( 1,1)]

    def bfs(start_r, start_c):
        """
        Flood-fill from (start_r, start_c).
        Returns (area, y1, y2, x1, x2) without keeping all pixel coords,
        saving memory on large blobs.
        """
        queue            = deque()
        queue.append((start_r, start_c))
        visited[start_r][start_c] = True

        area = 0
        y1 = y2 = start_r
        x1 = x2 = start_c

        while queue:
            r, c = queue.popleft()          # O(1) — key fix over original
            area += 1

            # track bounding box inline — no separate min/max pass
            if r < y1: y1 = r
            if r > y2: y2 = r
            if c < x1: x1 = c
            if c > x2: x2 = c

            for dr, dc in NEIGHBOURS:
                nr, nc = r + dr, c + dc
                if (0 <= nr < h and 0 <= nc < w
                        and not visited[nr][nc]
                        and binary[nr][nc] == 1):
                    visited[nr][nc] = True
                    queue.append((nr, nc))

        return area, y1, y2, x1, x2

    for r in range(h):
        for c in range(w):
            if binary[r][c] == 1 and not visited[r][c]:
                area, y1, y2, x1, x2 = bfs(r, c)

                if area < min_blob_area:
                    continue

                bh = y2 - y1 + 1
                bw = x2 - x1 + 1
                box_area = bh * bw

                # Fix 2: discard embedded images / figures
                if box_area > max_box_area:
                    continue

                blobs.append({
                    "x1":          x1,
                    "y1":          y1,
                    "x2":          x2,
                    "y2":          y2,
                    "height":      bh,
                    "width":       bw,
                    "area":        area,
                    "fill_ratio":  area / box_area if box_area > 0 else 0.0,
                    "aspect_ratio":bw / bh if bh > 0 else 0.0,
                    "center_r":    (y1 + y2) / 2.0,
                    "center_c":    (x1 + x2) / 2.0,
                })

    return blobs


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 4 — Font size estimation
# ═══════════════════════════════════════════════════════════════════════════════

def estimate_font_size(blobs):
    """
    Estimate the dominant body-text glyph height in pixels.

    Algorithm
    ---------
    1. Compute the median blob height across all blobs.
    2. Discard blobs taller than 3× the median — these are likely
       equation structures, tall brackets, or multi-line regions that
       would inflate the mode if left in.
    3. Build a height histogram on the filtered set.
    4. Smooth with a 3-bin window and return the peak.
       (Smoothing prevents a noisy tie between adjacent heights, e.g.
        height=11 vs height=12 both having count=47.)

    Falls back to 20 px if blobs is empty.

    Parameters
    ----------
    blobs : list of blob dicts from find_all_blobs()

    Returns
    -------
    int  estimated font height in pixels

    Notes
    -----
    Enhancement over original:
    - Giant-blob filter (3× median) before building the histogram
    - 3-bin smoothed peak instead of raw argmax
    """
    if not blobs:
        return 20

    # ── Step 1: exclude structural math symbols from the vote ───────────────
    # Integral signs, tall brackets, parentheses etc. have very low
    # aspect_ratio (tall & thin, ar < 0.4) and low fill_ratio (< 0.3).
    # They are NOT representative of body-text glyph height and must be
    # excluded before building the histogram.
    # Also exclude blobs shorter than 4 px (noise fragments / stray dots).
    MIN_HEIGHT  = 4
    MIN_ASPECT  = 0.4    # below this → tall thin math symbol, not a glyph
    candidates  = [b for b in blobs
                   if b["height"] >= MIN_HEIGHT
                   and b["aspect_ratio"] >= MIN_ASPECT]

    if not candidates:          # degenerate — fall back to all blobs
        candidates = blobs

    # ── Step 2: percentile-based height range ────────────────────────────────
    # Use p10–p90 window to get a robust range, then apply a 3× median cutoff
    # to discard any remaining tall outliers (merged glyphs, sub/superscripts).
    heights_all = sorted(b["height"] for b in candidates)
    n_all       = len(heights_all)
    p10         = heights_all[max(0, int(0.10 * n_all))]
    p90         = heights_all[min(n_all - 1, int(0.90 * n_all))]

    min_height  = max(MIN_HEIGHT, p10)
    max_height  = p90 * 2
    filtered    = [b["height"] for b in candidates
                   if min_height <= b["height"] <= max_height]

    if not filtered:
        filtered = heights_all

    # recompute median on filtered set for the 3× cutoff
    filtered_s = sorted(filtered)
    median     = filtered_s[len(filtered_s) // 2]
    cutoff     = median * 3
    filtered   = [h for h in filtered if h <= cutoff]
    if not filtered:
        filtered = filtered_s

    # ── Step 3: height histogram ─────────────────────────────────────────────
    hist = {}
    for h in filtered:
        hist[h] = hist.get(h, 0) + 1

    # ── Step 4: 3-bin smoothed peak ──────────────────────────────────────────
    # For each height h, sum counts of h-1, h, h+1 and pick the max
    best_h     = filtered[0]
    best_score = -1
    for h in hist:
        score = (hist.get(h - 1, 0) +
                 hist.get(h,     0) +
                 hist.get(h + 1, 0))
        if score > best_score:
            best_score = score
            best_h     = h

    return best_h


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 5 — Group blobs into regions  (Union-Find with path compression)
# ═══════════════════════════════════════════════════════════════════════════════

def group_blobs_into_regions(blobs, font_size,
                              h_gap_factor=2.3, v_gap_factor=1.2,
                              min_blobs_per_region=2):
    """
    Cluster spatially proximate blobs into coherent text/equation regions
    using a Union-Find (disjoint-set) structure.

    Two blobs i, j are merged when:
        vertical gap   between their boxes  ≤  font_size × v_gap_factor
        horizontal gap between their boxes  ≤  font_size × h_gap_factor

    Parameters
    ----------
    blobs                : list of blob dicts from find_all_blobs()
    font_size            : int  from estimate_font_size()
    h_gap_factor         : float  horizontal tolerance multiplier
    v_gap_factor         : float  vertical tolerance multiplier
    min_blobs_per_region : int  regions with fewer blobs are discarded

    Returns
    -------
    list of region dicts  (see module docstring for schema)

    Notes
    -----
    Enhancements over original:
    - min_blobs_per_region is a parameter, not hardcoded
    - width, height, blob_count, density added to region dict
    - path compression kept (same as original)
    - v_gap early-break kept (same as original — good optimisation)
    """
    if not blobs:
        return []

    h_gap        = font_size * h_gap_factor
    v_gap        = font_size * v_gap_factor
    sorted_blobs = sorted(blobs, key=lambda b: (b["y1"], b["x1"]))
    n            = len(sorted_blobs)
    parent       = list(range(n))

    # ── Union-Find with path compression (kept from original) ────────────────
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]  # path halving
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    # ── Proximity pass ────────────────────────────────────────────────────────
    for i in range(n):
        bi = sorted_blobs[i]
        for j in range(i + 1, n):
            bj = sorted_blobs[j]
            # v_gap early-break: blobs are sorted by y1 so once the next
            # blob's top edge is more than v_gap below bi's bottom, no
            # further blob can possibly be close enough vertically
            if bj["y1"] - bi["y2"] > v_gap:
                break
            v_dist = max(0, bj["y1"] - bi["y2"])
            h_dist = max(0, max(bi["x1"], bj["x1"]) - min(bi["x2"], bj["x2"]))
            if v_dist <= v_gap and h_dist <= h_gap:
                union(i, j)

    # ── Collect groups ────────────────────────────────────────────────────────
    groups = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(sorted_blobs[i])

    # ── Build region dicts ────────────────────────────────────────────────────
    regions = []
    for group_blobs in groups.values():
        if len(group_blobs) < min_blobs_per_region:
            continue

        rx1 = min(b["x1"] for b in group_blobs)
        ry1 = min(b["y1"] for b in group_blobs)
        rx2 = max(b["x2"] for b in group_blobs)
        ry2 = max(b["y2"] for b in group_blobs)

        rw       = rx2 - rx1 + 1
        rh       = ry2 - ry1 + 1
        box_area = rw * rh
        ink_area = sum(b["area"] for b in group_blobs)

        regions.append({
            "x1":         rx1,
            "y1":         ry1,
            "x2":         rx2,
            "y2":         ry2,
            "width":      rw,
            "height":     rh,
            "blobs":      group_blobs,
            "blob_count": len(group_blobs),
            "density":    ink_area / box_area if box_area > 0 else 0.0,
        })

    return regions


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def run_blob_analysis(binary, min_blob_area=5, max_blob_area_ratio=0.05,
                      min_blobs_per_region=2):
    """
    Run the full blob analysis pipeline on a binarized image.

    Parameters
    ----------
    binary               : 2-D list[list[int]]  from preprocessing.preprocess()
    min_blob_area        : int    minimum ink pixels to keep a blob
    max_blob_area_ratio  : float  blobs whose box exceeds this fraction of
                                  image area are discarded (photos, figures)
    min_blobs_per_region : int    minimum blobs to keep a region

    Returns
    -------
    dict with keys:
        blobs      — list of blob dicts
        font_size  — int  estimated body-text height in pixels
        regions    — list of region dicts
    """
    blobs     = find_all_blobs(binary, min_blob_area=min_blob_area,
                               max_blob_area_ratio=max_blob_area_ratio)
    font_size = estimate_font_size(blobs)
    regions   = group_blobs_into_regions(
        blobs, font_size,
        min_blobs_per_region=min_blobs_per_region
    )

    return {
        "blobs":     blobs,
        "font_size": font_size,
        "regions":   regions,
    }
