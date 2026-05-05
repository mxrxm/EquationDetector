"""
blob_analysis.py 
================
"""

from collections import deque

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — Connected Component Analysis (BFS, 8-connected)
# ═══════════════════════════════════════════════════════════════════════════════

def find_all_blobs(binary, min_blob_area=5, max_blob_area_ratio=0.05):
    h, w         = len(binary), len(binary[0])
    img_area     = h * w
    max_box_area = img_area * max_blob_area_ratio
    visited      = [[False] * w for _ in range(h)]
    blobs        = []

    NEIGHBOURS = [(-1,-1),(-1,0),(-1,1),
                  ( 0,-1),       ( 0,1),
                  ( 1,-1),( 1,0),( 1,1)]

    def bfs(start_r, start_c):
        queue = deque()
        queue.append((start_r, start_c))
        visited[start_r][start_c] = True
        area = 0
        y1 = y2 = start_r
        x1 = x2 = start_c
        while queue:
            r, c = queue.popleft()
            area += 1
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
                if box_area > max_box_area:
                    continue
                blobs.append({
                    "x1":           x1,
                    "y1":           y1,
                    "x2":           x2,
                    "y2":           y2,
                    "height":       bh,
                    "width":        bw,
                    "area":         area,
                    "fill_ratio":   area / box_area if box_area > 0 else 0.0,
                    "aspect_ratio": bw / bh if bh > 0 else 0.0,
                    "center_r":     (y1 + y2) / 2.0,
                    "center_c":     (x1 + x2) / 2.0,
                })
    return blobs
# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 4 — Font size estimation
# ═══════════════════════════════════════════════════════════════════════════════

def estimate_font_size(blobs):
    if not blobs:
        return 20
    # Exclude very small blobs (punctuation, dots) which drag the mode down
    # Use blobs with area > 10 and height > 4 for estimation
    candidates = [b for b in blobs if b["area"] > 10 and b["height"] > 4]
    if not candidates:
        candidates = blobs
    hist = {}
    for b in candidates:
        hist[b["height"]] = hist.get(b["height"], 0) + 1
    font_size = max(hist, key=hist.get)
    print(f"  Estimated font size: {font_size}px")
    return font_size

# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def run_blob_analysis(binary, min_blob_area=5,max_blob_area_ratio=0.03):
    """
    Run the full blob analysis pipeline on a binarized image.

    Parameters
    ----------
    binary               : 2-D list[list[int]]  from preprocessing.preprocess()
    min_blob_area        : int    minimum ink pixels to keep a blob
    max_blob_area_ratio  : float  blobs whose box > this fraction of image
                                  area are discarded (photos, figures)

    Returns
    -------
    dict:  blobs, font_size
    """
    blobs     = find_all_blobs(binary,
                               min_blob_area=min_blob_area,
                               max_blob_area_ratio=max_blob_area_ratio)
    font_size = estimate_font_size(blobs)

    return {"blobs": blobs, "font_size": font_size}