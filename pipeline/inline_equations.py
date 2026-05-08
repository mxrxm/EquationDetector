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

v2 changes (false-positive reduction):
  - has_strong: tall+tiny condition now requires v_spread > 1.2 (was any)
    → italic body text with an adjacent subscript/period no longer fires
  - has_strong: math_operatorish path requires tiny_count >= 3 when
    v_spread <= 1.0 (was tiny_count >= 2) — narrows trigger on math-looking
    punctuation in normal prose
  - New hard reject "small_italic_word": n <= 5, body_ratio > 0.55, no frac,
    v_spread < 1.0 — catches isolated italic variable mentions like "x_i"
  - all_body check widened to 0.50–1.55 (was 0.55–1.5) so italic glyphs
    that render slightly tall are still treated as body-height
  - score_threshold raised 3.5 → 4.5
  - delta_threshold raised 5.0 → 6.5
  - baseline_max tightened 1.5 → 0.8: only run on lines that look
    predominantly text-like (low baseline score)
  - strong_delta adaptive floor raised 3.5 → 4.5
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
    n = len(cluster_blobs)

    if n < 2:
        has_frac = any(
            b["width"] > font_size * 1.2 and
            b["height"] <= max(2, font_size * 0.15)
            for b in cluster_blobs
        )
        is_very_tall = any(b["height"] > font_size * 2.8 for b in cluster_blobs)
        if has_frac or is_very_tall:
            return 4.0, True, {"reason": "single_strong_symbol"}
        return -10.0, False, {"reason": "too_small"}

    if n > max_cluster_size * 1.5:
        return -10.0, False, {"reason": "too_large"}

    span = max(b["x2"] for b in cluster_blobs) - min(b["x1"] for b in cluster_blobs)
    if span < font_size * 0.9:
        return -10.0, False, {"reason": "too_narrow"}

    heights   = [b["height"] for b in cluster_blobs]
    widths    = [b["width"]  for b in cluster_blobs]
    aspects   = [b["aspect_ratio"] for b in cluster_blobs]
    centers_r = [b["center_r"] for b in cluster_blobs]

    mean_h  = sum(heights) / n
    cv_h    = _cv(heights)
    cv_ar   = _cv(aspects)
    h_ratio = mean_h / font_size

    has_frac = any(
        b["width"]  > font_size * frac_width_ratio and
        b["height"] <= max(2, font_size * frac_height_ratio)
        for b in cluster_blobs
    )

    tall_count = sum(1 for b in cluster_blobs if b["height"] > font_size * tall_height_ratio)
    tall_ratio = tall_count / n

    tiny_count = sum(1 for b in cluster_blobs if b["height"] < font_size * tiny_height_ratio)
    tiny_ratio = tiny_count / n

    v_spread = (max(centers_r) - min(centers_r)) / font_size

    body_count = sum(1 for b in cluster_blobs
                     if font_size * 0.60 <= b["height"] <= font_size * 1.45)
    body_ratio = body_count / n

    wide_flat = sum(
        1 for b in cluster_blobs
        if b["width"] > font_size * 0.8 and b["height"] < font_size * 0.35
    )

    # All operator-like shapes
    operatorish = sum(
        1 for b in cluster_blobs
        if b["aspect_ratio"] > 2.2 or b["aspect_ratio"] < 0.35
    )
    # Parenthesis-shaped blobs: tall thin — these appear in normal prose
    paren_count = sum(
        1 for b in cluster_blobs
        if b["aspect_ratio"] < 0.45 and b["height"] > font_size * 0.5
    )
    # Math-specific operators only (parens alone don't prove equations)
    math_operatorish = max(0, operatorish - paren_count)

    # ── Hard reject: overwhelmingly body-height blobs ──────────────────
    if body_ratio > 0.85 and not has_frac and tall_count == 0 and tiny_count == 0:
        return -10.0, False, {"reason": "all_body_height"}

    # ── Hard reject: word-in-parentheses label, e.g. "(Efficiency):" ──
    sorted_x = sorted(cluster_blobs, key=lambda b: b["x1"])
    paren_blobs = [b for b in sorted_x
                   if b["aspect_ratio"] < 0.45 and b["height"] > font_size * 0.5]
    # FIX v2: only reject paren_label when there are NO tiny (subscript)
    # blobs inside. Real math like f(x_S∪{i}) has subscript blobs;
    # text labels like "(Efficiency):" consist entirely of body-height letters.
    if len(paren_blobs) >= 2 and body_ratio > 0.50 and tiny_count == 0:
        leftmost_paren_x  = paren_blobs[0]["x1"]
        rightmost_paren_x = paren_blobs[-1]["x2"]
        cluster_x1 = sorted_x[0]["x1"]
        cluster_x2 = sorted_x[-1]["x2"]
        paren_spans = (
            leftmost_paren_x  - cluster_x1 < font_size * 0.8 and
            cluster_x2 - rightmost_paren_x < font_size * 0.8
        )
        if paren_spans:
            return -10.0, False, {"reason": "paren_label"}
    # Before the small_italic_word check, detect explicit = sign
    has_equals_like = any(
        b["aspect_ratio"] > 1.8 and 
        font_size * 0.08 <= b["height"] <= font_size * 0.35 and
        b["width"] > font_size * 0.4
        for b in cluster_blobs
    )

    if (n <= 8 and body_ratio > 0.55 and not has_frac
            and tall_count == 0 and v_spread < 1.0
            and math_operatorish <= 1 and wide_flat == 0
            and not has_equals_like):          # <-- add this guard
        return -10.0, False, {"reason": "small_italic_word"}
    # ── Hard reject: citation bracket, e.g. "[13]" ────────────────────
    bracket_like = sum(
        1 for b in cluster_blobs
        if b["aspect_ratio"] > 1.6 and b["height"] < font_size * 0.9
    )
    if (n <= 6 and bracket_like >= 2 and
            tall_count == 0 and not has_frac and
            tiny_count == 0 and v_spread < 0.6):
        return -10.0, False, {"reason": "citation_bracket"}

    # ── Hard reject: small italic word with subscript/period ──────────
    # FIX v2: isolated italic variable mentions like "x_i", "f(·)_κ",
    # "N" with a tiny superscript are NOT inline equations.
    # Pattern: small cluster (≤8 blobs), mostly body-height, no frac,
    # vertical spread stays compact (sub/superscript doesn't stack far
    # enough to exceed v_spread 1.0 on a real math expression).
    if (n <= 8 and body_ratio > 0.55 and not has_frac
            and tall_count == 0 and v_spread < 1.0
            and math_operatorish <= 1 and wide_flat == 0):
        return -10.0, False, {"reason": "small_italic_word"}

    # ── Text guards ────────────────────────────────────────────────────
    texty = (
        body_ratio > 0.76 and cv_h < 0.30 and cv_ar < 0.60 and v_spread < 0.9
        and tall_count == 0 and tiny_count == 0 and not has_frac
        and math_operatorish == 0 and wide_flat == 0
    )
    if texty:
        return -10.0, False, {"reason": "texty"}

    if (body_ratio > 0.72 and tall_count == 0 and not has_frac and
            tiny_count <= 1 and math_operatorish < 2 and wide_flat == 0 and v_spread < 0.9):
        return -10.0, False, {"reason": "texty_weak"}

    if (n > 18 and body_ratio > 0.82 and not has_frac and
            tall_count == 0 and tiny_count == 0 and v_spread < 0.6):
        return -10.0, False, {"reason": "large_texty"}

    if (n >= sentence_min_n and body_ratio > 0.72 and not has_frac and tall_count == 0 and
            math_operatorish == 0 and tiny_count <= 1 and v_spread < 0.8):
        return -10.0, False, {"reason": "sentence_text"}

    # ── has_strong ─────────────────────────────────────────────────────
    # FIX v2: The tall+tiny combinations now require v_spread > 1.0 (2+ tiny)
    # or v_spread > 1.3 (single tiny).
    #
    # Rationale: in body text, an italic letter like "i" or "f" that
    # renders slightly tall (tall_count=1) sitting next to a period or
    # comma (tiny_count=1) has v_spread < 0.5 because the sub/superscript
    # is not truly stacked — it just touches the baseline area.
    # Real inline math sub/superscripts (e.g. x_{i+1}^{2}) force blobs
    # above the cap-line AND below the baseline, pushing v_spread > 1.0.
    # Using 1.0 for the stronger tall+tiny conditions and 1.3 for the
    # weakest single-pair condition keeps the false-positive gap large.
    #
    # The math_operatorish path: raised tiny requirement when v_spread ≤ 1.0
    # to prevent ≜, ∈, \ symbols in semi-formal notation from triggering.
    has_strong = (
        has_frac
        or (tall_count >= 2 and tiny_count >= 1 and v_spread > 1.0)   # v2: 1.2→1.0
        or (tall_count >= 1 and tiny_count >= 2 and v_spread > 1.0)   # v2: 1.2→1.0
        or (tall_count >= 1 and tiny_count >= 1 and v_spread > 1.3)   # v2: 1.5→1.3
        or (wide_flat >= 2 and (tall_count >= 1 or tiny_count >= 1))
        # v2: math_operatorish path — require more tiny blobs when spread is low
        or (math_operatorish >= 2 and tiny_count >= 3 and v_spread > 0.8)        # low spread case
        or (math_operatorish >= 2 and tiny_count >= 2 and v_spread > 1.2)        # high spread case
        or (math_operatorish >= 3 and v_spread > 0.8 and tiny_count >= 1)        # many operators
        or (has_equals_like and tiny_count >= 1 and n <= 10 and v_spread > 0.3)
    )

    if n > max_cluster_size:
        if not (has_frac or (tiny_count >= 3 and v_spread > 0.9) or
                (tall_count >= 1 and tiny_count >= 1) or
                (math_operatorish >= 2 and tiny_count >= 1)):
            return -10.0, False, {"reason": "too_large"}

    # ── Scoring ────────────────────────────────────────────────────────
    score = 0.0

    if has_frac:                score += 4.0
    if tall_ratio > 0.10:       score += 2.5
    elif tall_ratio > 0.05:     score += 1.5
    if tiny_ratio > 0.10:       score += 2.0
    elif tiny_ratio > 0.05:     score += 1.0
    if tiny_count >= 2 and v_spread > 0.8:
        score += 1.2
    if cv_h > 0.50:             score += 1.5
    if cv_h > 0.80:             score += 1.5
    if cv_ar > 0.60:            score += 0.5
    if h_ratio > 1.35:          score += 1.0
    if v_spread > 0.8:          score += 0.5
    if wide_flat >= 1:          score += 0.5
    if math_operatorish >= 2:   score += 0.8
    if has_equals_like and tiny_count >= 1:
        score += 3.0   # strong signal: operator + superscript = algebra
    # ── Penalties ──────────────────────────────────────────────────────
    if cv_h < 0.18 and not has_frac:
        score -= 3.5
    if tall_count == 0 and tiny_count == 0 and not has_frac:
        score -= 2.5
    if body_ratio > 0.70 and not has_frac and tiny_count == 0:
        score -= 2.0

    mid_count = n - tall_count - tiny_count
    if ((mid_count / n) > 0.42 and
            v_spread < 0.85 and
            wide_flat == 0 and
            not has_frac and
            tiny_count <= 1 and
            math_operatorish == 0):
        score -= 6.0

    if n <= 4 and cv_h < 0.20 and not has_frac and math_operatorish == 0:
        score -= 3.0

    if (n <= 6 and v_spread < 0.6 and cv_h < 0.25 and cv_ar < 0.45 and
            tall_count == 0 and tiny_count == 0 and not has_frac and math_operatorish == 0):
        return -10.0, False, {"reason": "short_text"}

    signals = {
        "n":               n,
        "cv_h":            round(cv_h, 3),
        "cv_ar":           round(cv_ar, 3),
        "h_ratio":         round(h_ratio, 3),
        "has_frac":        has_frac,
        "tall_count":      tall_count,
        "tiny_count":      tiny_count,
        "v_spread":        round(v_spread, 3),
        "body_ratio":      round(body_ratio, 3),
        "wide_flat":       wide_flat,
        "operatorish":     operatorish,
        "math_operatorish": math_operatorish,
        "paren_count":     paren_count,
        "span_px":         span,
        "texty":           texty,
    }

    return score, has_strong, signals


# ─────────────────────────────────────────
# STEP 4 — Detect inline equations in all text regions
# ─────────────────────────────────────────

def detect_inline_equations(text_regions, font_size,
                             score_threshold=4.5,      # v2: raised from 3.5
                             delta_threshold=6.5,      # v2: raised from 5.0
                             gap_factor=0.9,
                             max_cluster_size=24,
                             sentence_min_n=12,
                             tiny_height_ratio=0.42,
                             frac_width_ratio=1.2,
                             frac_height_ratio=0.15,
                             tall_height_ratio=1.9,
                             baseline_max=0.8,         # v2: tightened from 1.5
                             debug=False):
    """
    Pass 2: word-cluster level inline equation detection.

    Parameters
    ----------
    text_regions     : list of region dicts (with "blobs" key)
                       — output of group_blobs_into_regions that was NOT
                         flagged as standalone equation in Pass 1
    font_size        : int — estimated body text height in px
    score_threshold  : float — minimum cluster score to consider (default 4.5)
                       v2 raised from 3.5 to reduce false positives on italic text
    delta_threshold  : float — how much above the line baseline a cluster
                       must score (default 6.5, v2 raised from 5.0)
    baseline_max     : float — maximum allowable line baseline score.
                       Lines whose median cluster score exceeds this are
                       considered "math-heavy" and skipped to avoid the
                       delta gate becoming vacuous. (v2: 0.8, was 1.5)
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

                # Adaptive delta: stronger math signals need less separation.
                # v2: raised floor from 3.5 → 4.5 to stay well above the
                # score level that italic-word false positives can reach.
                strong_delta = delta_threshold
                if sigs.get("has_frac") or (sigs.get("tiny_count", 0) >= 1 and sigs.get("operatorish", 0) >= 1):
                    strong_delta = max(4.5, delta_threshold - 1.5)   # v2: floor 3.5→4.5

                # FIX v2: widen "all_body" band to 0.50–1.55 so italic
                # glyphs that render 5–10% taller than font_size still count
                # as body-height and reject via this gate rather than slipping
                # through with all_body=False.
                all_body = all(
                    font_size * 0.50 <= b["height"] <= font_size * 1.55
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
                    pad  = int(font_size * 0.3)
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