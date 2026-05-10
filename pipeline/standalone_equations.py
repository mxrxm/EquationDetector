import math


# ─────────────────────────────────────────────────────────────────────────────
# Per-density config
# density_class: 0 = sparse (few blobs/line, wide spacing)
#                1 = medium
#                2 = dense  (packed text, small font, tight spacing)
# ─────────────────────────────────────────────────────────────────────────────

_DENSITY_CFG = {
    0: dict(
        # Sparse docs — equations tend to be isolated, few blobs, trust structure
        score_threshold       = 4,
        confidence_cutoff     = 0.35,
        frac_bar_w_factor     = 0.8,
        frac_bar_h_factor     = 0.22,
        frac_bar_score        = 4,
        tall_sym_threshold    = 0.02,
        tall_sym_score        = 4,
        cv_h_low              = 0.35,
        cv_h_high             = 0.80,
        outlier_low           = 0.08,
        outlier_high          = 0.25,
        height_ratio_min      = 1.2,
        region_ar_bonus       = 2.0,
        single_line_body_ratio= 0.70,
        small_blob_max        = 14,
        small_h_ratio_max     = 1.5,
        wide_uniform_ar       = 3,
        para_h_ratio          = 5.0,
        para_cv_h             = 0.65,
        font_size_small       = 10,
    ),
    1: dict(
        # Medium density — balanced defaults
        score_threshold       = 5,
        confidence_cutoff     = 0.4,
        frac_bar_w_factor     = 1.0,
        frac_bar_h_factor     = 0.20,
        frac_bar_score        = 3,
        tall_sym_threshold    = 0.04,
        tall_sym_score        = 2,
        cv_h_low              = 0.50,
        cv_h_high             = 1.00,
        outlier_low           = 0.05,
        outlier_high          = 0.50,
        height_ratio_min      = 1.8,
        region_ar_bonus       = 3.0,
        single_line_body_ratio= 0.60,
        small_blob_max        = 12,
        small_h_ratio_max     = 1.7,
        wide_uniform_ar       = 3,
        para_h_ratio          = 4.0,
        para_cv_h             = 0.55,
        font_size_small       = 12,
    ),
    2: dict(
        # Dense docs — stricter to avoid false positives from packed text
        score_threshold       = 7,
        confidence_cutoff     = 0.45,
        frac_bar_w_factor     = 1.2,
        frac_bar_h_factor     = 0.16,
        frac_bar_score        = 3,
        tall_sym_threshold    = 0.05,
        tall_sym_score        = 2,
        cv_h_low              = 0.60,
        cv_h_high             = 1.10,
        outlier_low           = 0.12,
        outlier_high          = 0.35,
        height_ratio_min      = 2.0,
        region_ar_bonus       = 2.5,
        single_line_body_ratio= 0.60,
        small_blob_max        = 10,
        small_h_ratio_max     = 1.9,
        wide_uniform_ar       = 3,
        para_h_ratio          = 3.5,
        para_cv_h             = 0.50,
        font_size_small       = 14,
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# NMS — suppress smaller boxes that are largely contained in a larger one
# ─────────────────────────────────────────────────────────────────────────────

def _suppress_nested_boxes(detections, overlap_threshold=0.7):
    if len(detections) <= 1:
        return detections

    def box_area(d):
        x1, y1, x2, y2 = d["box"]
        return (x2 - x1) * (y2 - y1)

    sorted_dets = sorted(detections, key=box_area, reverse=True)
    keep = [True] * len(sorted_dets)

    for i in range(len(sorted_dets)):
        if not keep[i]:
            continue
        ax1, ay1, ax2, ay2 = sorted_dets[i]["box"]
        for j in range(i + 1, len(sorted_dets)):
            if not keep[j]:
                continue
            bx1, by1, bx2, by2 = sorted_dets[j]["box"]
            ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
            ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
            if ix2 <= ix1 or iy2 <= iy1:
                continue
            inter_area = (ix2 - ix1) * (iy2 - iy1)
            b_area     = (bx2 - bx1) * (by2 - by1)
            if b_area == 0:
                continue
            if inter_area / b_area >= overlap_threshold:
                keep[j] = False

    return [d for d, k in zip(sorted_dets, keep) if k]


# ─────────────────────────────────────────────────────────────────────────────
# Main detector
# ─────────────────────────────────────────────────────────────────────────────

def detect_standalone_equations(regions, font_size, img_height,
                                 density_class=1,
                                 img_width=None,
                                 top_margin=0.05, debug=False):
    """
    Scores every region and returns those that pass as standalone
    (display-mode) equations — class 0.

    Parameters
    ----------
    regions       : output of group_blobs_into_regions()
    font_size     : estimated font size in pixels
    img_height    : full image height in pixels
    density_class : 0 (sparse) / 1 (medium) / 2 (dense) from doc-type detector
    img_width     : full image width in pixels (optional — enables centering signal)
    top_margin    : fraction of image height to skip at the top
    debug         : print per-region score breakdown

    Returns
    -------
    List of dicts: {"box": (x1,y1,x2,y2), "confidence": float, "class": 0}
    """
    cfg       = _DENSITY_CFG[density_class]
    MAX_SCORE = 20.0
    margin    = img_height * top_margin
    results   = []

    for region in regions:
        x1, y1, x2, y2 = region["x1"], region["y1"], region["x2"], region["y2"]

        if y2 < margin:
            continue

        blobs = region["blobs"]
        w, h  = x2 - x1, y2 - y1
        if w == 0 or h == 0 or len(blobs) < 2:
            continue

        # ── Feature extraction ────────────────────────────────────────────

        heights = [b["height"] for b in blobs]
        mean_h  = sum(heights) / len(heights)
        var_h   = sum((v - mean_h) ** 2 for v in heights) / len(heights)
        cv_h    = math.sqrt(var_h) / mean_h if mean_h > 0 else 0

        aspects = [b["aspect_ratio"] for b in blobs]
        mean_ar = sum(aspects) / len(aspects)
        var_ar  = sum((v - mean_ar) ** 2 for v in aspects) / len(aspects)
        cv_ar   = math.sqrt(var_ar) / mean_ar if mean_ar > 0 else 0

        tall_blobs = sum(1 for b in blobs if b["height"] > font_size * 1.8)
        wide_blobs = sum(1 for b in blobs
                         if b["width"]  > font_size * 4.0
                         and b["height"] < font_size * 0.5)

        frac_bars = sum(1 for b in blobs
                        if b["width"]  >  font_size * cfg["frac_bar_w_factor"]
                        and b["height"] <= max(2, font_size * cfg["frac_bar_h_factor"]))

        tall_symbols   = sum(1 for b in blobs if b["height"] > font_size * 1.5)
        tall_sym_ratio = tall_symbols / len(blobs)
        outlier_ratio  = (tall_blobs + wide_blobs) / len(blobs)

        height_ratio = h / font_size
        region_ar    = w / h if h > 0 else 0
        mean_h_ratio = mean_h / font_size if font_size > 0 else 1.0

        centers     = [b["center_r"] for b in blobs]
        center_span = (max(centers) - min(centers)) / font_size

        body_like  = sum(1 for b in blobs
                         if font_size * 0.6 <= b["height"] <= font_size * 1.4)
        body_ratio = body_like / len(blobs)

        region_center = (y1 + y2) / 2
        band_half     = font_size * 0.35
        band_like     = sum(1 for c in centers
                            if abs(c - region_center) <= band_half)
        band_ratio    = band_like / len(blobs)

        blob_area  = sum(b["area"] for b in blobs)
        area_ratio = blob_area / max(1, w * h)

        # Blobs per font-height unit — paragraphs are dense, equations sparse
        blobs_per_lh = len(blobs) / max(1.0, height_ratio)

        # Text density — blobs per estimated character width
        text_density = len(blobs) / max(1, w / font_size)

        # Centering bonus — display equations are typically centered on the page
        centered_bonus = False
        if img_width and img_width > 0:
            page_cx      = img_width / 2.0
            region_cx    = (x1 + x2) / 2.0
            offset_ratio = abs(region_cx - page_cx) / img_width
            narrower     = w < img_width * 0.75
            centered_bonus = (offset_ratio < 0.20 and narrower)

        # Edge-outlier penalty — bullet points / equation numbers at page edges
        outlier_blobs_list = [b for b in blobs
                              if b["height"] > font_size * 1.8 or
                              (b["width"] > font_size * 4.0
                               and b["height"] < font_size * 0.5)]
        edge_outlier_penalty = False
        if outlier_blobs_list and len(blobs) > 10:
            outlier_centers_c = [b["center_c"] for b in outlier_blobs_list]
            left_edge  = x1 + w * 0.15
            right_edge = x1 + w * 0.85
            edge_outliers = sum(1 for c in outlier_centers_c
                                if c < left_edge or c > right_edge)
            if edge_outliers == len(outlier_blobs_list) and region_ar > 8:
                edge_outlier_penalty = True

        # Operator-like blobs (=, +, -, ×, etc.)
        operator_like  = sum(1 for b in blobs
                             if 0.3 < b["aspect_ratio"] < 3.0
                             and b["height"] < font_size * 1.3)
        operator_ratio = operator_like / len(blobs)

        # ── Scoring ───────────────────────────────────────────────────────
        score = 0

        if cv_h > cfg["cv_h_low"]:               score += 2
        if cv_h > cfg["cv_h_high"]:              score += 2
        if cv_ar > 0.8:                           score += 1
        if outlier_ratio > cfg["outlier_low"]:   score += 2
        if outlier_ratio > cfg["outlier_high"]:  score += 3
        if blobs_per_lh < 4:                      score += 3
        elif blobs_per_lh < 12:                   score += 1
        if height_ratio > cfg["height_ratio_min"]: score += 1
        if region_ar < cfg["region_ar_bonus"]:   score += 1
        if center_span > 1.2:                     score += 1
        if body_ratio < 0.4:                      score += 1
        if frac_bars >= 1:                        score += cfg["frac_bar_score"]
        if tall_sym_ratio > cfg["tall_sym_threshold"]:
            score += cfg["tall_sym_score"]        # applied exactly once
        if centered_bonus and cv_h > 0.45:        score += 1
        if operator_ratio > 0.18:                 score += 2

        # Mixed-structure bonus
        if cv_h > 0.7 and cv_ar > 0.6 and body_ratio < 0.4:
            score += 3

        # Penalties
        if cv_h < 0.2 and height_ratio < 1.3:         score -= 3
        if region_ar > 8 and h < font_size * 1.3:    score -= 4
        if center_span < 0.7:                          score -= 2
        if body_ratio > 0.7 and height_ratio < 1.6:   score -= 2
        if band_ratio > 0.7 and height_ratio < 1.6:   score -= 1
        if area_ratio > 0.35 and height_ratio > 2.5:  score -= 2
        if edge_outlier_penalty:                       score -= 4

        # ── Hard guards ───────────────────────────────────────────────────
        # Applied after scoring so debug output shows the pre-guard score.
        # text_density guard runs here (not before scoring) so rescue can still fire.

        # Very packed text — too dense to be an equation
        if text_density > 2.5 and cv_h < 0.45:
            score = -99

        # Heading: large mean height, few blobs, uniform — but not if it has
        # tall symbols or fraction bars (those indicate real equation content)
        if (mean_h_ratio > 1.6 and height_ratio < 5.0
                and len(blobs) < 40 and cv_h < 0.5
                and tall_sym_ratio < 0.05
                and frac_bars == 0):
            score = -99

        # Single wide text line
        if (region_ar > 4 and height_ratio < 1.5
                and center_span < 0.9
                and body_ratio > cfg["single_line_body_ratio"]):
            score = -99

        # Small uniform region (single word / label)
        if (len(blobs) <= cfg["small_blob_max"]
                and height_ratio < cfg["small_h_ratio_max"]
                and center_span < 1.0
                and body_ratio > 0.5
                and band_ratio > 0.5):
            score = -99

        # Wide uniform band (header / footer lines)
        if (region_ar > cfg["wide_uniform_ar"]
                and cv_h < 0.5 and cv_ar < 0.5 and band_ratio > 0.6):
            score = -99

        # Multi-line paragraph block
        if (height_ratio > cfg["para_h_ratio"]
                and cv_h < cfg["para_cv_h"]
                and outlier_ratio < 0.10 and body_ratio > 0.45):
            score = -99

        # Tall paragraph block
        if (height_ratio > 6.0 and cv_h < 0.55
                and outlier_ratio < 0.12 and body_ratio > 0.50):
            score = -99

        # Very wide flat region
        if region_ar > 15 and height_ratio < 4.0 and cv_h < 0.55:
            score = -99

        # Small font guard
        if font_size <= cfg["font_size_small"]:
            if cv_h < 0.65 and frac_bars == 0 and tall_sym_ratio < 0.05:
                score = -99

        # ── Rescue: structural signals override soft guards ───────────────
        # A fraction bar or tall symbol in a non-text-line region is strong
        # evidence of a real equation even if a guard fired above.
        is_clear_text_line = (region_ar > 6 and height_ratio < 1.5
                              and center_span < 0.9
                              and body_ratio > cfg["single_line_body_ratio"])

        if score == -99 and not is_clear_text_line:
            if frac_bars >= 1 and height_ratio > 2.0 and region_ar < 5.0:
                score = cfg["frac_bar_score"] + 2
            elif tall_sym_ratio > cfg["tall_sym_threshold"] and height_ratio > 2.5:
                score = 5

        if debug:
            tag = "EQ" if score >= cfg["score_threshold"] else "TEXT"
            print(f"  ({x1},{y1})-({x2},{y2}) blobs={len(blobs):3d} "
                  f"cv_h={cv_h:.2f} outliers={outlier_ratio:.2f} "
                  f"h_ratio={height_ratio:.1f} bpl_h={blobs_per_lh:.1f} "
                  f"ar={region_ar:.1f} frac={frac_bars} "
                  f"tall={tall_sym_ratio:.2f} ctr={centered_bonus} "
                  f"score={score:+d} → {tag}")

        if score < cfg["score_threshold"]:
            continue

        confidence = min(1.0, max(0.0, score / MAX_SCORE))
        if confidence <= cfg["confidence_cutoff"]:
            continue

        results.append({
            "box":        (x1, y1, x2, y2),
            "confidence": round(confidence, 3),
            "class":      0,
        })

    return _suppress_nested_boxes(results, overlap_threshold=0.7)