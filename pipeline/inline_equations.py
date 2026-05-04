"""
Inline equation detection (Pass 2): detect_inline_equations.

Operates on text regions that Pass 1 did not flag as standalone equations.
Decomposes each region into lines, then into word clusters, then scores
each cluster for equation-like properties.

Key design decisions vs the original:
  - score_delta threshold lowered from 8.0 → 5.0 (was rejecting real equations)
  - has_strong relaxed: single tall+tiny pair now counts on research papers
  - baseline computed more robustly (median instead of mean to resist outliers)
  - hallucination guards tightened: body_ratio > 0.85 hard-rejects a cluster
  - confidence gate removed — let the caller filter by threshold
  - MAX_SCORE = 11.5 kept; scoring weights rebalanced
"""

import math


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def _median(values):
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _cv(values):
    """Coefficient of variation — std / mean. Returns 0 if mean is 0."""
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(var) / mean


# ─────────────────────────────────────────
# STEP 1 — Split region blobs into lines
# ─────────────────────────────────────────

def split_region_into_lines(region_blobs, font_size, v_gap_factor=0.6):
    """
    Group blobs into horizontal lines by vertical proximity.
    A gap larger than (font_size × v_gap_factor) starts a new line.
    """
    if not region_blobs:
        return []

    v_gap        = font_size * v_gap_factor
    sorted_blobs = sorted(region_blobs, key=lambda b: b["center_r"])
    lines        = []
    current      = [sorted_blobs[0]]

    for blob in sorted_blobs[1:]:
        # Use gap between bounding boxes, not centers
        gap = blob["y1"] - current[-1]["y2"]
        if gap > v_gap:
            lines.append(current)
            current = [blob]
        else:
            current.append(blob)

    lines.append(current)
    return lines


# ─────────────────────────────────────────
# STEP 2 — Split line blobs into word clusters
# ─────────────────────────────────────────

def split_line_into_word_clusters(line_blobs, font_size, gap_factor=0.9):
    """
    Group blobs within a line into word-sized clusters by horizontal proximity.
    gap_factor controls how big a gap must be to start a new cluster.
    Slightly tighter than before (0.9 vs 1.2) to avoid merging adjacent words.
    """
    if not line_blobs:
        return []

    max_gap      = font_size * gap_factor
    sorted_blobs = sorted(line_blobs, key=lambda b: b["x1"])
    clusters     = []
    current      = [sorted_blobs[0]]

    for blob in sorted_blobs[1:]:
        gap = blob["x1"] - current[-1]["x2"]
        if gap > max_gap:
            clusters.append(current)
            current = [blob]
        else:
            current.append(blob)

    clusters.append(current)
    return clusters


# ─────────────────────────────────────────
# STEP 3 — Score a single cluster
# ─────────────────────────────────────────

def score_cluster_as_equation(cluster_blobs, font_size, max_cluster_size=24,
                              sentence_min_n=12,
                              tiny_height_ratio=0.42,
                              frac_width_ratio=1.2,
                              frac_height_ratio=0.15,
                              tall_height_ratio=1.9):
    """
    Score a word cluster for equation likelihood.

    Returns
    -------
    score      : float   — higher = more equation-like
    has_strong : bool    — True if at least one unambiguous math signal present
    signals    : dict    — raw measurements for debug printing
    """
    n = len(cluster_blobs)

    # ── Hard reject: cluster too small ──────────────────────────────────
    if n < 2:
        # Only pass if it's an unambiguous single symbol
        has_frac = any(
            b["width"] > font_size * 1.2 and
            b["height"] <= max(2, font_size * 0.15)
            for b in cluster_blobs
        )
        is_very_tall = any(b["height"] > font_size * 2.8 for b in cluster_blobs)
        if has_frac or is_very_tall:
            return 4.0, True, {"reason": "single_strong_symbol"}
        return -10.0, False, {"reason": "too_small"}

    # ── Hard reject: cluster too large (full text line leaked through) ───
    if n > max_cluster_size * 1.5:
        return -10.0, False, {"reason": "too_large"}

    # ── Hard reject: cluster too narrow ──────────────────────────────────
    span = max(b["x2"] for b in cluster_blobs) - min(b["x1"] for b in cluster_blobs)
    if span < font_size * 0.9:
        return -10.0, False, {"reason": "too_narrow"}

    # ── Compute features ─────────────────────────────────────────────────
    heights    = [b["height"] for b in cluster_blobs]
    widths     = [b["width"]  for b in cluster_blobs]
    aspects    = [b["aspect_ratio"] for b in cluster_blobs]
    centers_r  = [b["center_r"] for b in cluster_blobs]

    mean_h     = sum(heights) / n
    cv_h       = _cv(heights)
    cv_ar      = _cv(aspects)
    h_ratio    = mean_h / font_size   # mean blob height relative to font

    # Fraction bar: very wide AND very flat
    # Thresholds tuned by frac_width_ratio and frac_height_ratio
    has_frac = any(
        b["width"]  > font_size * frac_width_ratio and
        b["height"] <= max(2, font_size * frac_height_ratio)
        for b in cluster_blobs
    )

    # Tall symbols: integral signs, tall brackets, summation
    # Threshold tuned by tall_height_ratio
    tall_count = sum(1 for b in cluster_blobs if b["height"] > font_size * tall_height_ratio)
    tall_ratio = tall_count / n

    # Tiny symbols: superscripts, subscripts, dots in equations
    # Threshold tuned by tiny_height_ratio
    tiny_count = sum(1 for b in cluster_blobs if b["height"] < font_size * tiny_height_ratio)
    tiny_ratio = tiny_count / n

    # Vertical spread of blob centers — equations have blobs at different heights
    v_spread = (max(centers_r) - min(centers_r)) / font_size

    # Body-height blobs — normal text letters
    body_count = sum(1 for b in cluster_blobs
                     if font_size * 0.60 <= b["height"] <= font_size * 1.45)
    body_ratio = body_count / n

    # Wide flat blobs other than fraction bars (minus signs, underlines)
    wide_flat = sum(
        1 for b in cluster_blobs
        if b["width"] > font_size * 0.8 and b["height"] < font_size * 0.35
    )

    # Operator-like shapes (very wide or very tall/skinny)
    operatorish = sum(
        1 for b in cluster_blobs
        if b["aspect_ratio"] > 2.2 or b["aspect_ratio"] < 0.35
    )

    # ── Hard reject: overwhelmingly body-height blobs ─────────────────
    # If >85% of blobs are normal letter height and no fraction bar or
    # tall/tiny symbols, this is definitely text — don't score it
    if body_ratio > 0.85 and not has_frac and tall_count == 0 and tiny_count == 0:
        return -10.0, False, {"reason": "all_body_height"}

    # Text-like cluster guard (single words / short phrases)
    texty = (
        body_ratio > 0.76 and cv_h < 0.30 and cv_ar < 0.60 and v_spread < 0.9
        and tall_count == 0 and tiny_count == 0 and not has_frac
        and operatorish == 0 and wide_flat == 0
    )
    if texty:
        return -10.0, False, {"reason": "texty"}

    # Weak text-like guard: allow dots on letters but still reject phrases
    if (body_ratio > 0.72 and tall_count == 0 and not has_frac and
            tiny_count <= 1 and operatorish < 2 and wide_flat == 0 and v_spread < 0.9):
        return -10.0, False, {"reason": "texty_weak"}

    # Large clusters that still look like plain text (avoid full-line leaks)
    if (n > 18 and body_ratio > 0.82 and not has_frac and
            tall_count == 0 and tiny_count == 0 and v_spread < 0.6):
        return -10.0, False, {"reason": "large_texty"}

    # Sentence-like guard: many blobs, mostly body height, low math structure
    if (n >= sentence_min_n and body_ratio > 0.72 and not has_frac and tall_count == 0 and
            operatorish == 0 and tiny_count <= 1 and v_spread < 0.8):
        return -10.0, False, {"reason": "sentence_text"}

    # ── has_strong: requires at least one unambiguous math feature ────────
    # Relaxed slightly from original to catch research paper inline equations:
    #   - Fraction bar alone is enough
    #   - tall≥2 + tiny≥1 (as before)
    #   - tall≥1 + tiny≥2 (as before)
    #   - tall≥1 + tiny≥1 + v_spread > 1.0 (new: catches x_i^2 style)
    has_strong = (
        has_frac
        or (tall_count >= 2 and tiny_count >= 1)
        or (tall_count >= 1 and tiny_count >= 2)
        or (tall_count >= 1 and tiny_count >= 1 and v_spread > 1.0)
        or (wide_flat >= 2 and (tall_count >= 1 or tiny_count >= 1))
        or (operatorish >= 2 and (tiny_count >= 2 or v_spread > 0.8))
    )

    # Allow larger clusters only if they show strong math structure
    if n > max_cluster_size:
        if not (has_frac or (tiny_count >= 3 and v_spread > 0.9) or
                (tall_count >= 1 and tiny_count >= 1) or
                (operatorish >= 2 and tiny_count >= 1)):
            return -10.0, False, {"reason": "too_large"}

    # ── Scoring ───────────────────────────────────────────────────────────
    score = 0.0

    if has_frac:                score += 4.0   # strongest signal
    if tall_ratio > 0.10:       score += 2.5
    elif tall_ratio > 0.05:     score += 1.5
    if tiny_ratio > 0.10:       score += 2.0
    elif tiny_ratio > 0.05:     score += 1.0
    if tiny_count >= 2 and v_spread > 0.8:
        score += 1.2
    if cv_h > 0.50:             score += 1.5
    if cv_h > 0.80:             score += 1.5   # additional for very high variance
    if cv_ar > 0.60:            score += 0.5
    if h_ratio > 1.35:          score += 1.0   # mean height above font line
    if v_spread > 0.8:          score += 0.5
    if wide_flat >= 1:          score += 0.5   # minus signs etc.
    if operatorish >= 2:        score += 0.8

    # ── Penalties ─────────────────────────────────────────────────────────
    # Very uniform heights with nothing special = text
    if cv_h < 0.18 and not has_frac:
        score -= 3.5
    # No tall or tiny blobs and no fraction bar = text
    if tall_count == 0 and tiny_count == 0 and not has_frac:
        score -= 2.5
    # Mostly body-height (but not caught by hard reject above)
    if body_ratio > 0.70 and not has_frac and tiny_count == 0:
        score -= 2.0
    
    # Heavy penalty for words disguised as math (like "(Efficiency):")
    # i.e., >50% normal letters, no math operators, no sub/superscript jumping
    mid_count = n - tall_count - tiny_count
    if (mid_count / n) > 0.48 and v_spread < 0.85 and wide_flat == 0 and not has_frac and tiny_count <= 1:
        score -= 6.0
        
    # Very small cluster with low variance = single word, not equation
    if n <= 4 and cv_h < 0.20 and not has_frac and operatorish == 0:
        score -= 3.0

    # Text-like short word guard: uniform shapes, low vertical spread
    if (n <= 6 and v_spread < 0.6 and cv_h < 0.25 and cv_ar < 0.45 and
            tall_count == 0 and tiny_count == 0 and not has_frac and operatorish == 0):
        return -10.0, False, {"reason": "short_text"}

    signals = {
        "n":           n,
        "cv_h":        round(cv_h, 3),
        "cv_ar":       round(cv_ar, 3),
        "h_ratio":     round(h_ratio, 3),
        "has_frac":    has_frac,
        "tall_count":  tall_count,
        "tiny_count":  tiny_count,
        "v_spread":    round(v_spread, 3),
        "body_ratio":  round(body_ratio, 3),
        "wide_flat":   wide_flat,
        "operatorish": operatorish,
        "span_px":     span,
        "texty":       texty,
    }

    return score, has_strong, signals


# ─────────────────────────────────────────
# STEP 4 — Detect inline equations in all text regions
# ─────────────────────────────────────────

def detect_inline_equations(text_regions, font_size,
                             score_threshold=3.5,
                             delta_threshold=5.0,
                             gap_factor=0.9,
                             max_cluster_size=24,
                             sentence_min_n=12,
                             tiny_height_ratio=0.42,
                             frac_width_ratio=1.2,
                             frac_height_ratio=0.15,
                             tall_height_ratio=1.9,
                             baseline_max=1.5,
                             debug=False):
    """
    Pass 2: word-cluster level inline equation detection.

    Parameters
    ----------
    text_regions     : list of region dicts (with "blobs" key)
                       — output of group_blobs_into_regions that was NOT
                         flagged as standalone equation in Pass 1
    font_size        : int — estimated body text height in px
    score_threshold  : float — minimum cluster score to consider (default 3.5)
                       Lower = more sensitive, higher = fewer false positives
    delta_threshold  : float — how much above the line baseline a cluster
                       must score (default 5.0, was 8.0 — too aggressive)
    debug            : bool — print per-cluster scores

    Returns
    -------
    list of dicts: {box: (x1,y1,x2,y2), confidence: float, class: 1}
    """
    MAX_SCORE      = 11.5
    inline_results = []

    for region in text_regions:
        # Accept both region dicts and plain tuples (skip tuples)
        if isinstance(region, tuple):
            continue
        if "blobs" not in region:
            continue

        lines = split_region_into_lines(region["blobs"], font_size)

        for line_blobs in lines:
            if not line_blobs:
                continue

            clusters = split_line_into_word_clusters(
                line_blobs, font_size, gap_factor=gap_factor
            )

            # Score every cluster on this line
            cluster_scores  = []
            cluster_signals = []
            cluster_strongs = []

            for cluster in clusters:
                s, strong, sigs = score_cluster_as_equation(
                    cluster,
                    font_size,
                    max_cluster_size=max_cluster_size,
                    sentence_min_n=sentence_min_n,
                    tiny_height_ratio=tiny_height_ratio,
                    frac_width_ratio=frac_width_ratio,
                    frac_height_ratio=frac_height_ratio,
                    tall_height_ratio=tall_height_ratio,
                )
                cluster_scores.append(s)
                cluster_strongs.append(strong)
                cluster_signals.append(sigs)

            # ── Baseline: robust median of non-candidate scores ───────────
            # Use median instead of mean to resist outliers
            non_candidate = [s for s in cluster_scores if s < 2.0]
            baseline = _median(non_candidate) if non_candidate else -2.0

            # ── Evaluate each cluster ─────────────────────────────────────
            for cluster, score, strong, sigs in zip(
                    clusters, cluster_scores, cluster_strongs, cluster_signals):

                score_delta = score - baseline

                # Adaptive delta: stronger math signals need less separation
                strong_delta = delta_threshold
                if sigs.get("has_frac") or (sigs.get("tiny_count", 0) >= 1 and sigs.get("operatorish", 0) >= 1):
                    strong_delta = max(3.5, delta_threshold - 1.5)

                # Check if all blobs are body-height (pure text)
                all_body = all(
                    font_size * 0.55 <= b["height"] <= font_size * 1.5
                    for b in cluster
                )

                # Final gate — all conditions must pass
                passes_score = (
                    score >= score_threshold or
                    (sigs.get("tiny_count", 0) >= 3 and sigs.get("v_spread", 0) > 0.9
                     and (sigs.get("operatorish", 0) >= 1 or sigs.get("tall_count", 0) >= 1)
                     and score_delta >= strong_delta + 1.5)
                )
                is_inline_eq = (
                    strong                          # unambiguous math feature
                    and passes_score               # absolute score or tiny+spread override
                    and score_delta >= strong_delta # anomalous vs line baseline
                    and not all_body               # at least one outlier blob
                    and baseline < baseline_max    # line mostly looks like text
                )

                if debug:
                    cx1 = min(b["x1"] for b in cluster)
                    cx2 = max(b["x2"] for b in cluster)
                    cy1 = min(b["y1"] for b in cluster)
                    cy2 = max(b["y2"] for b in cluster)
                    tag = "▶ EQ" if is_inline_eq else "   "
                    if "reason" in sigs:
                        print(f"  {tag} x=[{cx1:4d},{cx2:4d}] rejected: {sigs['reason']}")
                    else:
                        print(
                            f"  {tag} x=[{cx1:4d},{cx2:4d}] "
                            f"n={sigs['n']:2d} "
                            f"cv_h={sigs['cv_h']:.2f} "
                            f"frac={sigs['has_frac']} "
                            f"tall={sigs['tall_count']} "
                            f"tiny={sigs['tiny_count']} "
                            f"body={sigs['body_ratio']:.2f} "
                            f"score={score:+.1f} "
                            f"base={baseline:+.1f} "
                            f"delta={score_delta:+.1f} "
                            f"strong={strong}"
                        )

                if is_inline_eq:
                    cx1 = min(b["x1"] for b in cluster)
                    cy1 = min(b["y1"] for b in cluster)
                    cx2 = max(b["x2"] for b in cluster)
                    cy2 = max(b["y2"] for b in cluster)
                    pad  = int(font_size * 0.3)   # tighter padding than before
                    conf = min(1.0, max(0.0, score / MAX_SCORE))

                    inline_results.append({
                        "box":        (
                            max(0, cx1 - pad),
                            max(0, cy1 - pad),
                            cx2 + pad,
                            cy2 + pad,
                        ),
                        "confidence": round(conf, 3),
                        "class":      1,
                    })

    return inline_results