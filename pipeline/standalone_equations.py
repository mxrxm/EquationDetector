# import math


# from pipeline.blob_analysis import run_blob_analysis
# import region_grouping
# import preprocessing



# # ─────────────────────────────────────────
# # Stage 6 — Classify regions → standalone equations only
# # Returns list of dicts {box, confidence, class=0}
# # ─────────────────────────────────────────

# def _suppress_nested_boxes(detections, overlap_threshold=0.7):
#     """
#     Remove boxes that are substantially contained within another box.
#     For each pair, if the smaller box overlaps the larger by more than
#     overlap_threshold (measured as intersection/smaller_box_area), drop it.
#     """
#     if len(detections) <= 1:
#         return detections

#     # Sort by box area descending — process larger boxes first
#     def box_area(d):
#         x1, y1, x2, y2 = d["box"]
#         return (x2 - x1) * (y2 - y1)

#     sorted_dets = sorted(detections, key=box_area, reverse=True)
#     keep = [True] * len(sorted_dets)

#     for i in range(len(sorted_dets)):
#         if not keep[i]:
#             continue
#         ax1, ay1, ax2, ay2 = sorted_dets[i]["box"]
#         for j in range(i + 1, len(sorted_dets)):
#             if not keep[j]:
#                 continue
#             bx1, by1, bx2, by2 = sorted_dets[j]["box"]

#             # Intersection
#             ix1 = max(ax1, bx1)
#             iy1 = max(ay1, by1)
#             ix2 = min(ax2, bx2)
#             iy2 = min(ay2, by2)

#             if ix2 <= ix1 or iy2 <= iy1:
#                 continue  # no overlap

#             inter_area = (ix2 - ix1) * (iy2 - iy1)
#             b_area     = (bx2 - bx1) * (by2 - by1)

#             if b_area == 0:
#                 continue

#             # If smaller box is mostly inside larger box → suppress smaller
#             if inter_area / b_area >= overlap_threshold:
#                 keep[j] = False

#     return [d for d, k in zip(sorted_dets, keep) if k]




# def detect_standalone_equations(regions, font_size, img_height,
#                                  top_margin=0.05, debug=False):
#     """
#     Scores every region and returns those that pass as standalone
#     (display-mode) equations — class 0.

#     Parameters
#     ----------
#     regions    : output of group_blobs_into_regions()
#     font_size  : estimated font size in pixels
#     img_height : full image height in pixels
#     top_margin : fraction of image height to skip at the top (header noise)
#     debug      : if True, prints per-region scores

#     Returns
#     -------
#     List of dicts: {"box": (x1,y1,x2,y2), "confidence": float, "class": 0}
#     """
#     MAX_SCORE  = 20.0
#     margin     = img_height * top_margin
#     results    = []

#     for region in regions:
#         x1, y1, x2, y2 = region["x1"], region["y1"], region["x2"], region["y2"]

#         # Skip header band
#         if y2 < margin:
#             continue

#         blobs = region["blobs"]
#         w, h  = x2 - x1, y2 - y1
#         if w == 0 or h == 0 or len(blobs) < 2:
#             continue

#         # ── Feature extraction ──────────────────────────────────────────
#         heights  = [b["height"] for b in blobs]
#         mean_h   = sum(heights) / len(heights)
#         var_h    = sum((x - mean_h) ** 2 for x in heights) / len(heights)
#         cv_h     = math.sqrt(var_h) / mean_h if mean_h > 0 else 0

#         aspects  = [b["aspect_ratio"] for b in blobs]
#         mean_ar  = sum(aspects) / len(aspects)
#         var_ar   = sum((x - mean_ar) ** 2 for x in aspects) / len(aspects)
#         cv_ar    = math.sqrt(var_ar) / mean_ar if mean_ar > 0 else 0

#         tall_blobs = sum(1 for b in blobs if b["height"] > font_size * 1.8)
#         wide_blobs = sum(1 for b in blobs if b["width"] > font_size * 4.0
#                          and b["height"] < font_size * 0.5)

#         # Fraction bars: wide AND very flat
#         frac_bars = sum(1 for b in blobs
#                         if b["width"] > font_size * 1.0
#                         and b["height"] <= max(2, font_size * 0.18))

#         # Tall symbols: Σ, integral signs
#         tall_symbols   = sum(1 for b in blobs if b["height"] > font_size * 1.5)
#         tall_sym_ratio = tall_symbols / len(blobs)
#         outlier_ratio  = (tall_blobs + wide_blobs) / len(blobs)

#         height_ratio = h / font_size
#         region_ar    = w / h if h > 0 else 0

#         centers     = [b["center_r"] for b in blobs]
#         center_span = (max(centers) - min(centers)) / font_size

#         body_like  = sum(1 for b in blobs
#                          if font_size * 0.6 <= b["height"] <= font_size * 1.4)
#         body_ratio = body_like / len(blobs)

#         region_center = (y1 + y2) / 2
#         band_half     = font_size * 0.35
#         band_like     = sum(1 for c in centers
#                             if abs(c - region_center) <= band_half)
#         band_ratio    = band_like / len(blobs)

#         blob_area  = sum(b["area"] for b in blobs)
#         area_ratio = blob_area / max(1, w * h)

#         # ── Edge-outlier detection (bullet / equation-number pattern) ───
#         # Fires when ALL outlier blobs are clustered on the left or right
#         # edge of a wide region — characteristic of a bullet point (left)
#         # or a parenthesised equation number like "(25.3)" (right).
#         outlier_blobs_list = [b for b in blobs
#                               if b["height"] > font_size * 1.8 or
#                               (b["width"] > font_size * 4.0
#                                and b["height"] < font_size * 0.5)]
#         edge_outlier_penalty = False
#         if outlier_blobs_list and len(blobs) > 10:
#             outlier_centers_c = [b["center_c"] for b in outlier_blobs_list]
#             left_edge         = x1 + w * 0.15
#             right_edge        = x1 + w * 0.85
#             edge_outliers     = sum(1 for c in outlier_centers_c
#                                     if c < left_edge or c > right_edge)
#             if edge_outliers == len(outlier_blobs_list) and region_ar > 8:
#                 edge_outlier_penalty = True

#         # ── Scoring ─────────────────────────────────────────────────────
#         score = 0

#         # Positive signals
#         if cv_h > 0.5:           score += 2
#         if cv_h > 1.0:           score += 2
#         if cv_ar > 0.8:          score += 1
#         if outlier_ratio > 0.1:  score += 2
#         if outlier_ratio > 0.3:  score += 3
#         if height_ratio > 1.8:   score += 2
#         if region_ar < 3.0:      score += 1
#         if center_span > 1.2:    score += 1
#         if body_ratio < 0.4:     score += 1
#         if frac_bars >= 1:       score += 3   # fraction bar — strong signal
#         if tall_sym_ratio > 0.04: score += 2  # Σ, ∫ present

#         # Penalties
#         if cv_h < 0.2 and height_ratio < 1.3:         score -= 3
#         if region_ar > 10 and h < font_size * 1.3:    score -= 4
#         if center_span < 0.7:                          score -= 2
#         if body_ratio > 0.7 and height_ratio < 1.6:   score -= 2
#         if band_ratio > 0.7 and height_ratio < 1.6:   score -= 1
#         if area_ratio > 0.35 and height_ratio > 2.5:  score -= 2
#         if edge_outlier_penalty:                       score -= 4

#         # Mixed-structure bonus (cv_h AND cv_ar both high, few body-height blobs)
#         if cv_h > 0.7 and cv_ar > 0.6 and body_ratio < 0.4:
#             score += 3

#         # ── Hard guards → reject ────────────────────────────────────────
#         mean_h_ratio = mean_h / font_size if font_size > 0 else 1.0
#         # Heading guard: all blobs are tall (mean height >> font_size) but region
#         # is shallow and has few blobs — characteristic of a bold section heading
#         if (mean_h_ratio > 1.6 and height_ratio < 5.0
#                 and len(blobs) < 40 and cv_h < 0.5):
#             score = -99
#         # Single wide text line
#         if (region_ar > 6 and height_ratio < 1.5
#                 and center_span < 0.9 and body_ratio > 0.6):
#             score = -99
        
#         # # Guard A: rotated text / watermark / sidebar — never taller than wide
#         # if region_ar < 1.0:
#         #     score = -99

#         # # Guard B: wide dense text block with many blobs — title, multi-line header
#         # if (region_ar > 10 and height_ratio < 10.0 and cv_h < 0.55
#         #         and len(blobs) > 60 and outlier_ratio < 0.35):
#         #     score = -99

#         # # Guard C: short uniform text phrase — author names, labels, short captions
#         # if (len(blobs) <= 30 and height_ratio < 3.0
#         #         and cv_h < 0.45 and outlier_ratio < 0.20
#         #         and band_ratio > 0.5):
#         #     score = -99


#         # Small uniform region — likely a short text phrase
#         if (len(blobs) <= 12 and height_ratio < 1.7
#                 and center_span < 1.0 and body_ratio > 0.5
#                 and band_ratio > 0.5):
#             score = -99

#         # Wide uniform band — justified text line
#         if (region_ar > 8 and cv_h < 0.5 and cv_ar < 0.5 and band_ratio > 0.6):
#             score = -99

#         # Multi-line block with low height variance — paragraph text
#         if (height_ratio > 4.0 and cv_h < 0.55
#                 and outlier_ratio < 0.15 and body_ratio > 0.45):
#             score = -99

#         # Tall paragraph block — even if cv_h is slightly higher,
#         # real equations rarely fill this many lines with body-height glyphs
#         if (height_ratio > 6.0 and cv_h < 0.55
#                 and outlier_ratio < 0.12 and body_ratio > 0.50):
#             score = -99

#         # Very wide flat region (title lines, long text lines) —
#         # height_ratio < 4.0 covers titles that span 3-4 line heights
#         if (region_ar > 15 and height_ratio < 4.0 and cv_h < 0.55):
#             score = -99
#         # When font_size is very small, outlier and height thresholds are unreliable.
#         # Require stronger evidence: higher cv_h and real structural signals.
#         if font_size <= 12:
#             if cv_h < 0.65 and frac_bars == 0 and tall_sym_ratio < 0.05:
#                 score = -99
#         if debug:
#             print(f"  ({x1},{y1})-({x2},{y2}) blobs={len(blobs):3d} "
#                   f"cv_h={cv_h:.2f} outliers={outlier_ratio:.2f} "
#                   f"h_ratio={height_ratio:.1f} ar={region_ar:.1f} "
#                   f"score={score:+d} → {'EQ' if score >= 5 else 'TEXT'}")

#         if score < 5:
#             continue

#         confidence = min(1.0, max(0.0, score / MAX_SCORE))

#         # Low-confidence detections are likely misclassified text
#         if confidence <= 0.35:
#             continue

#         results.append({
#             "box":        (x1, y1, x2, y2),
#             "confidence": round(confidence, 3),
#             "class":      0,
#         })
#     results = _suppress_nested_boxes(results, overlap_threshold=0.7)
#     return results  

import math


from pipeline.blob_analysis import run_blob_analysis
import region_grouping
import preprocessing



# ─────────────────────────────────────────
# Stage 6 — Classify regions → standalone equations only
# Returns list of dicts {box, confidence, class=0}
# ─────────────────────────────────────────

def _suppress_nested_boxes(detections, overlap_threshold=0.7):
    """
    Remove boxes that are substantially contained within another box.
    For each pair, if the smaller box overlaps the larger by more than
    overlap_threshold (measured as intersection/smaller_box_area), drop it.
    """
    if len(detections) <= 1:
        return detections

    # Sort by box area descending — process larger boxes first
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

            # Intersection
            ix1 = max(ax1, bx1)
            iy1 = max(ay1, by1)
            ix2 = min(ax2, bx2)
            iy2 = min(ay2, by2)

            if ix2 <= ix1 or iy2 <= iy1:
                continue  # no overlap

            inter_area = (ix2 - ix1) * (iy2 - iy1)
            b_area     = (bx2 - bx1) * (by2 - by1)

            if b_area == 0:
                continue

            # If smaller box is mostly inside larger box → suppress smaller
            if inter_area / b_area >= overlap_threshold:
                keep[j] = False

    return [d for d, k in zip(sorted_dets, keep) if k]




def detect_standalone_equations(regions, font_size, img_height,
                                 top_margin=0.05, debug=False):
    """
    Scores every region and returns those that pass as standalone
    (display-mode) equations — class 0.

    Parameters
    ----------
    regions    : output of group_blobs_into_regions()
    font_size  : estimated font size in pixels
    img_height : full image height in pixels
    top_margin : fraction of image height to skip at the top (header noise)
    debug      : if True, prints per-region scores

    Returns
    -------
    List of dicts: {"box": (x1,y1,x2,y2), "confidence": float, "class": 0}
    """
    MAX_SCORE  = 20.0
    margin     = img_height * top_margin
    results    = []

    for region in regions:
        x1, y1, x2, y2 = region["x1"], region["y1"], region["x2"], region["y2"]

        # Skip header band
        if y2 < margin:
            continue

        blobs = region["blobs"]
        w, h  = x2 - x1, y2 - y1
        if w == 0 or h == 0 or len(blobs) < 2:
            continue

        # ── Feature extraction ──────────────────────────────────────────
        heights  = [b["height"] for b in blobs]
        mean_h   = sum(heights) / len(heights)
        var_h    = sum((x - mean_h) ** 2 for x in heights) / len(heights)
        cv_h     = math.sqrt(var_h) / mean_h if mean_h > 0 else 0

        aspects  = [b["aspect_ratio"] for b in blobs]
        mean_ar  = sum(aspects) / len(aspects)
        var_ar   = sum((x - mean_ar) ** 2 for x in aspects) / len(aspects)
        cv_ar    = math.sqrt(var_ar) / mean_ar if mean_ar > 0 else 0

        tall_blobs = sum(1 for b in blobs if b["height"] > font_size * 1.8)
        wide_blobs = sum(1 for b in blobs if b["width"] > font_size * 4.0
                         and b["height"] < font_size * 0.5)

        # Fraction bars: wide AND very flat
        frac_bars = sum(1 for b in blobs
                        if b["width"] > font_size * 1.0
                        and b["height"] <= max(2, font_size * 0.18))

        # Tall symbols: Σ, integral signs
        tall_symbols   = sum(1 for b in blobs if b["height"] > font_size * 1.5)
        tall_sym_ratio = tall_symbols / len(blobs)
        outlier_ratio  = (tall_blobs + wide_blobs) / len(blobs)

        height_ratio = h / font_size
        region_ar    = w / h if h > 0 else 0

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

        # ── Edge-outlier detection (bullet / equation-number pattern) ───
        # Fires when ALL outlier blobs are clustered on the left or right
        # edge of a wide region — characteristic of a bullet point (left)
        # or a parenthesised equation number like "(25.3)" (right).
        outlier_blobs_list = [b for b in blobs
                              if b["height"] > font_size * 1.8 or
                              (b["width"] > font_size * 4.0
                               and b["height"] < font_size * 0.5)]
        edge_outlier_penalty = False
        if outlier_blobs_list and len(blobs) > 10:
            outlier_centers_c = [b["center_c"] for b in outlier_blobs_list]
            left_edge         = x1 + w * 0.15
            right_edge        = x1 + w * 0.85
            edge_outliers     = sum(1 for c in outlier_centers_c
                                    if c < left_edge or c > right_edge)
            if edge_outliers == len(outlier_blobs_list) and region_ar > 8:
                edge_outlier_penalty = True

        # ── Scoring ─────────────────────────────────────────────────────
        score = 0

        # Positive signals
        if cv_h > 0.5:           score += 2
        if cv_h > 1.0:           score += 2
        if cv_ar > 0.8:          score += 1
        if outlier_ratio > 0.1:  score += 2
        if outlier_ratio > 0.3:  score += 3
        if height_ratio > 1.8:   score += 2
        if region_ar < 3.0:      score += 1
        if center_span > 1.2:    score += 1
        if body_ratio < 0.4:     score += 1
        if frac_bars >= 1:       score += 3   # fraction bar — strong signal
        if tall_sym_ratio > 0.04: score += 2  # Σ, ∫ present

        # Penalties
        if cv_h < 0.2 and height_ratio < 1.3:         score -= 3
        if region_ar > 10 and h < font_size * 1.3:    score -= 4
        if center_span < 0.7:                          score -= 2
        if body_ratio > 0.7 and height_ratio < 1.6:   score -= 2
        if band_ratio > 0.7 and height_ratio < 1.6:   score -= 1
        if area_ratio > 0.35 and height_ratio > 2.5:  score -= 2
        if edge_outlier_penalty:                       score -= 4

        # Mixed-structure bonus (cv_h AND cv_ar both high, few body-height blobs)
        if cv_h > 0.7 and cv_ar > 0.6 and body_ratio < 0.4:
            score += 3

        # ── Hard guards → reject ────────────────────────────────────────
        mean_h_ratio = mean_h / font_size if font_size > 0 else 1.0

        # Heading guard: all blobs are tall (mean height >> font_size) but region
        # is shallow and has few blobs — characteristic of a bold section heading.
        # Fraction bars are impossible in plain headings, so exempt them.
        if (mean_h_ratio > 1.6 and height_ratio < 5.0
                and len(blobs) < 40 and cv_h < 0.5
                and frac_bars == 0):                   # ← exempt fraction-bar regions
            score = -99

        # Single wide text line.
        # Exempt if a fraction bar is present (e.g. eq 25.4: dC/C = -dx/x) or
        # if glyphs are visually mixed (cv_ar elevated by subscripts/greek).
        if (region_ar > 6 and height_ratio < 1.5
                and center_span < 0.9 and body_ratio > 0.6
                and frac_bars == 0                     # ← exempt fraction-bar regions
                and cv_ar < 0.5):                      # ← exempt mixed-glyph lines
            score = -99

        # Small uniform region — likely a short text phrase.
        # Exempt if a fraction bar is present (definitive equation evidence) or
        # if height variance is elevated (sub/superscripts raise cv_h).
        if (len(blobs) <= 12 and height_ratio < 1.7
                and center_span < 1.0 and body_ratio > 0.5
                and band_ratio > 0.5
                and frac_bars == 0                     # ← exempt fraction-bar regions
                and cv_h < 0.45):                      # ← exempt mixed-height regions
            score = -99

        # Wide uniform band — justified text line.
        # Exempt if fraction bars are present.
        if (region_ar > 8 and cv_h < 0.5 and cv_ar < 0.5
                and band_ratio > 0.6
                and frac_bars == 0):                   # ← exempt fraction-bar regions
            score = -99

        # Multi-line block with low height variance — paragraph text
        if (height_ratio > 4.0 and cv_h < 0.55
                and outlier_ratio < 0.15 and body_ratio > 0.45):
            score = -99

        # Tall paragraph block — even if cv_h is slightly higher,
        # real equations rarely fill this many lines with body-height glyphs
        if (height_ratio > 6.0 and cv_h < 0.55
                and outlier_ratio < 0.12 and body_ratio > 0.50):
            score = -99

        # Very wide flat region (title lines, long text lines).
        # Exempt fraction-bar regions — a wide fraction is still an equation.
        if (region_ar > 15 and height_ratio < 4.0
                and cv_h < 0.55
                and frac_bars == 0):                   # ← exempt fraction-bar regions
            score = -99

        # Small-font guard: when font_size is very small, outlier and height
        # thresholds are unreliable so we require stronger structural evidence.
        # Previously this killed single-line equations with no fraction bar
        # (e.g. eq 25.6: C = ε₀w[ε₂l − (ε₂−ε₁)x]) because cv_h is low for
        # uniform-height glyphs and there are no tall symbols.
        # Fix: also allow through regions where:
        #   - cv_ar is elevated (subscripts/greek raise aspect variance), OR
        #   - the region has enough blobs to be confidently non-text.
        if font_size <= 12:
            if (cv_h < 0.65 and frac_bars == 0
                    and tall_sym_ratio < 0.05
                    and cv_ar < 0.55              # ← allow mixed-ar single-line eqs
                    and len(blobs) < 20):         # ← allow larger regions through
                score = -99

        if debug:
            print(f"  ({x1},{y1})-({x2},{y2}) blobs={len(blobs):3d} "
                  f"cv_h={cv_h:.2f} cv_ar={cv_ar:.2f} "
                  f"outliers={outlier_ratio:.2f} frac_bars={frac_bars} "
                  f"h_ratio={height_ratio:.1f} ar={region_ar:.1f} "
                  f"score={score:+d} → {'EQ' if score >= 4 else 'TEXT'}")

        # ── Pass threshold ───────────────────────────────────────────────
        # Lower the score gate slightly for fraction-bar regions: a fraction
        # bar is strong structural evidence that compensates for a modest total.
        min_score = 3 if frac_bars >= 1 else 5
        if score < min_score:
            continue

        confidence = min(1.0, max(0.0, score / MAX_SCORE))

        # Lower the confidence floor — compact equations score modestly
        # but are still genuine detections.
        if confidence <= 0.25:                         # ← was 0.35
            continue

        results.append({
            "box":        (x1, y1, x2, y2),
            "confidence": round(confidence, 3),
            "class":      0,
        })

    results = _suppress_nested_boxes(results, overlap_threshold=0.7)
    return results