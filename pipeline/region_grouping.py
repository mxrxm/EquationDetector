"""Region grouping: group_blobs_into_regions."""


def group_blobs_into_regions(blobs, font_size,
                              h_gap_factor=2.0, v_gap_factor=1.5):
    if not blobs:
        return []

    h_gap = font_size * h_gap_factor
    v_gap = font_size * v_gap_factor
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
        root = find(i)
        groups.setdefault(root, []).append(sorted_blobs[i])

    regions = []
    for group_blobs in groups.values():
        if len(group_blobs) < 2:
            continue
        regions.append({
            "x1":   min(b["x1"] for b in group_blobs),
            "y1":   min(b["y1"] for b in group_blobs),
            "x2":   max(b["x2"] for b in group_blobs),
            "y2":   max(b["y2"] for b in group_blobs),
            "blobs": group_blobs,
        })

    print(f"  Regions after grouping: {len(regions)}")
    return regions

