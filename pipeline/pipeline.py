# """
# pipeline/pipeline.py — Main orchestrator for the Equation Detector.

# Usage
# -----
# from pipeline.pipeline import run_cca_pipeline

# gray, binary, blobs, font_size, text_boxes, eq_results = run_cca_pipeline(
#     "paper.png",
#     detector_mode="combined",   # "blob" | "edge" | "combined"
#     debug=False
# )

# Returns
# -------
# gray       : 2-D list[int]   grayscale pixel values (0-255)
# binary     : 2-D list[int]   binarized image (1=ink, 0=background)
# blobs      : list[dict]      every ink blob with shape features
# font_size  : int             estimated body-text glyph height in px
# text_boxes : list[tuple]     (x1,y1,x2,y2) of regions classified as text
# eq_results : list[dict]      {box, confidence, class}
#                              class 0 = standalone / display equation
#                              class 1 = inline equation
# """

# import os
# import sys

# # ── make sibling imports work regardless of working directory ─────────────────
# _HERE = os.path.dirname(os.path.abspath(__file__))
# _ROOT = os.path.dirname(_HERE)
# for _p in (_HERE, _ROOT):
#     if _p not in sys.path:
#         sys.path.insert(0, _p)

# from pipeline.frame_line_detector import filter_line_blobs
# from region_grouping import group_blobs_into_regions
# from preprocessing        import preprocess
# from blob_analysis        import run_blob_analysis
# from standalone_equations import detect_standalone_equations
# from inline_equations     import detect_inline_equations


# # ── Document-type detection (graceful fallback if module missing) ─────────────
# try:
#     from .document_type import get_detector as _get_detector
#     _HAS_DOC_TYPE = True
# except ImportError as e:
#     print(f"[WARNING] document_type module not found: {e}. Using fallback.")
#     _HAS_DOC_TYPE = False


# def _detect_doc_type(blobs, font_size, width, height, gray, mode, debug):
#     if _HAS_DOC_TYPE:
#         detector = _get_detector(mode)
#         result   = detector.detect(
#             blobs      = blobs,
#             img_width  = width,
#             img_height = height,
#             font_size  = font_size,
#             gray       = gray,      
#         )
#         return result.doc_type, result.confidence

#     # Inline fallback — mirrors BlobDocumentTypeDetector thresholds
#     total_ink      = sum(b["area"] for b in blobs)
#     ink_density    = total_ink / max(1, width * height)
#     body_blobs     = sum(1 for b in blobs
#                          if font_size * 0.6 <= b["height"] <= font_size * 1.4)
#     body_ratio     = body_blobs / len(blobs) if blobs else 0
#     est_lines      = height / max(1, font_size * 1.5)
#     blobs_per_line = len(blobs) / max(1, est_lines)

#     is_dense = (ink_density    >  0.04
#                 and body_ratio >= 0.60
#                 and blobs_per_line > 25)
#     return ("dense" if is_dense else "sparse"), 0.7


# # ════════════════════════════════════════════════════════════════════════════════
# # PUBLIC ENTRY POINT
# # ════════════════════════════════════════════════════════════════════════════════

# def run_cca_pipeline(image_path,
#                      detector_mode="combined",
#                      inline_score_threshold=3.5,
#                      inline_delta_threshold=5.0,
#                      inline_gap_factor=0.9,
#                      inline_max_cluster_size=24,
#                      inline_sentence_min_n=12,
#                      inline_tiny_height_ratio=0.42,
#                      inline_frac_width_ratio=1.2,
#                      inline_frac_height_ratio=0.15,
#                      inline_tall_height_ratio=1.9,
#                      inline_baseline_max=1.5,
#                      debug=False):
#     """
#     Run the full equation-detection pipeline on one document image.

#     Parameters
#     ----------
#     image_path    : str   path to any PIL-readable image
#     detector_mode : str   "blob" | "edge" | "combined"  (default "combined")
#     debug         : bool  print per-region / per-cluster scores to stdout

#     Returns
#     -------
#     gray, binary, blobs, font_size, text_boxes, eq_results
#     """

#     # ── Stages 1 & 2 — Preprocessing ─────────────────────────────────────────
#     print(f"[1/5] Preprocessing: {os.path.basename(image_path)}")
#     pre      = preprocess(image_path)
#     gray     = pre["gray"]
#     binary   = pre["binary"]
#     width    = pre["width"]
#     height   = pre["height"]
#     print(f"      {width}×{height}px ")

#     # ── Stages 3-5 — Blob analysis (CCA + font-size + grouping) ──────────────
#     print("[2/5] Blob analysis...")
#     blob_res  = run_blob_analysis(binary)
#     blobs     = blob_res["blobs"]
#     font_size = blob_res["font_size"]
#     print(f"      blobs={len(blobs)}  font_size={font_size}px  ")

#     # ── Document type ─────────────────────────────────────────────────────────
#     print(f"[3/5] Document-type detection (mode={detector_mode!r})...")
#     doc_type, dt_conf = _detect_doc_type(
#         blobs, font_size, width, height, gray, detector_mode, debug
#     )
#     print(f"      → {doc_type.upper()}  (conf={dt_conf:.0%})")

#     filter_res= filter_line_blobs(blobs, width, height, font_size)
#     blobs=filter_res["clean_blobs"]
#     rejcted=filter_res["rejected_blobs"]
#     reasons=filter_res["rejection_reasons"]
#     print(f"      blobs rejected={len(rejcted)}  reasons={reasons}  ")
#     # ── Pass 1 — Standalone equations ─────────────────────────────────────────
#     print("[4/5] Pass 1 — standalone equation classification...")
#     regions =group_blobs_into_regions(blobs, font_size,
#                               h_gap_factor=2.3, line_v_factor=0.6,   
#                                         para_v_factor=None)

#     eq_results_p1 = detect_standalone_equations(
#         regions, font_size, height,
#         top_margin=0.05,
#         debug=debug
#     )

#     # Text boxes = all regions Pass 1 did NOT flag
#     eq_boxes_set = {d["box"] for d in eq_results_p1}
#     text_boxes   = [
#         (r["x1"], r["y1"], r["x2"], r["y2"])
#         for r in regions
#         if (r["x1"], r["y1"], r["x2"], r["y2"]) not in eq_boxes_set
#     ]
#     print(f"      standalone={len(eq_results_p1)}  text_regions={len(text_boxes)}")

#     # ── Pass 2 — Inline equations (dense documents only) ──────────────────────
#     eq_results_p2 = []
#     if doc_type == "dense":
#         print("[5/5] Pass 2 — inline equation detection...")
#         text_regions_with_blobs = [
#             r for r in regions
#             if (r["x1"], r["y1"], r["x2"], r["y2"]) not in eq_boxes_set
#         ]
#         eq_results_p2 = detect_inline_equations(
#             text_regions_with_blobs,
#             font_size,
#             score_threshold=inline_score_threshold,
#             delta_threshold=inline_delta_threshold,
#             gap_factor=inline_gap_factor,
#             max_cluster_size=inline_max_cluster_size,
#             sentence_min_n=inline_sentence_min_n,
#             tiny_height_ratio=inline_tiny_height_ratio,
#             frac_width_ratio=inline_frac_width_ratio,
#             frac_height_ratio=inline_frac_height_ratio,
#             tall_height_ratio=inline_tall_height_ratio,
#             baseline_max=inline_baseline_max,
#             debug=debug
#         )
#         print(f"      inline={len(eq_results_p2)}")
#     else:
#         print("[5/5] Pass 2 skipped (sparse document)")

#     # ── Final summary ─────────────────────────────────────────────────────────
#     eq_results = eq_results_p1 + eq_results_p2
#     print(f"\n── Results ──────────────────────────")
#     print(f"   Text regions    : {len(text_boxes)}")
#     print(f"   Standalone (c0) : {len(eq_results_p1)}")
#     print(f"   Inline     (c1) : {len(eq_results_p2)}")
#     print(f"   Total equations : {len(eq_results)}")
#     print(f"─────────────────────────────────────\n")

#     return gray, binary, blobs, font_size, text_boxes, eq_results


"""
pipeline/pipeline.py — Main orchestrator for the Equation Detector.

Usage
-----
    from pipeline.pipeline import run_cca_pipeline

    gray, binary, blobs, font_size, text_boxes, eq_results = run_cca_pipeline(
        "paper.png",
        debug=False,
    )

Returns
-------
    gray        : 2-D list[int]   grayscale pixel values (0-255)
    binary      : 2-D list[int]   binarized image (1=ink, 0=background)
    blobs       : list[dict]      every ink blob with shape features
    font_size   : int             estimated body-text glyph height in px
    text_boxes  : list[tuple]     (x1,y1,x2,y2) of regions classified as text
    eq_results  : list[dict]      {box, confidence, class}
                                  class 0 = standalone / display equation
                                  class 1 = inline equation

Density classes
---------------
    0  SPARSE  — exam sheets, assignment pages, slides
    1  MEDIUM  — lecture notes, light annotations, mixed slides
    2  DENSE   — research papers, textbooks, proceedings

density_class is forwarded to detect_standalone_equations() to select the
right scoring thresholds, and gates the inline-equation pass (class >= 1 only).
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pipeline.frame_line_detector import filter_line_blobs
from region_grouping               import group_blobs_into_regions
from preprocessing                 import preprocess
from blob_analysis                 import run_blob_analysis
from standalone_equations          import detect_standalone_equations
from inline_equations              import detect_inline_equations


# ── Document density detection (graceful fallback if module missing) ──────────
try:
    from .document_type import get_detector as _get_detector
    _HAS_DOC_TYPE = True
except ImportError as e:
    print(f"[WARNING] document_type module not found: {e}. Using inline fallback.")
    _HAS_DOC_TYPE = False


def _detect_density(blobs, font_size, width, height, debug):
    """
    Returns (density_class: int, confidence: float).
    density_class: 0=sparse, 1=medium, 2=dense.
    """
    if _HAS_DOC_TYPE:
        result = _get_detector("blob").detect(
            blobs=blobs, img_width=width, img_height=height,
            font_size=font_size, debug=debug,
        )
        return result.density_class, result.confidence

    # ── Inline fallback (mirrors BlobDocumentTypeDetector exactly) ────────────
    if not blobs:
        return 0, 1.0

    total_ink      = sum(b["area"] for b in blobs)
    ink_density    = total_ink / max(1, width * height)
    body_blobs     = sum(1 for b in blobs
                         if font_size * 0.6 <= b["height"] <= font_size * 1.4)
    body_ratio     = body_blobs / len(blobs)
    est_lines      = height / max(1, font_size * 1.5)
    blobs_per_line = len(blobs) / max(1, est_lines)

    def vote(v, lo, hi):
        return -1 if v < lo else (1 if v >= hi else 0)

    vote_sum = (vote(ink_density,    0.025, 0.055) +
                vote(body_ratio,     0.45,  0.65)  +
                vote(blobs_per_line, 12,    25))

    if vote_sum == 3:   return 2, 0.90
    if vote_sum == -3:  return 0, 0.90
    if vote_sum >= 1:   return 1, 0.65
    if vote_sum <= -1:  return 0, 0.70
    return 1, 0.60


_DENSITY_LABELS = {0: "SPARSE", 1: "MEDIUM", 2: "DENSE"}


# ════════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════════

def run_cca_pipeline(image_path,
                     inline_score_threshold=3.5,
                     inline_delta_threshold=5.0,
                     inline_gap_factor=0.9,
                     inline_max_cluster_size=24,
                     inline_sentence_min_n=12,
                     inline_tiny_height_ratio=0.42,
                     inline_frac_width_ratio=1.2,
                     inline_frac_height_ratio=0.15,
                     inline_tall_height_ratio=1.9,
                     inline_baseline_max=1.5,
                     debug=False):
    """
    Run the full equation-detection pipeline on one document image.

    Parameters
    ----------
    image_path : str   path to any PIL-readable image
    debug      : bool  print per-region / per-cluster scores

    Returns
    -------
    gray, binary, blobs, font_size, text_boxes, eq_results
    """

    # ── Stage 1 — Preprocessing ───────────────────────────────────────────────
    print(f"[1/5] Preprocessing: {os.path.basename(image_path)}")
    pre    = preprocess(image_path)
    gray   = pre["gray"]
    binary = pre["binary"]
    width  = pre["width"]
    height = pre["height"]
    print(f"      {width}×{height}px")

    # ── Stage 2 — Blob analysis ───────────────────────────────────────────────
    print("[2/5] Blob analysis...")
    blob_res  = run_blob_analysis(binary)
    blobs     = blob_res["blobs"]
    font_size = blob_res["font_size"]
    print(f"      blobs={len(blobs)}  font_size={font_size}px")

    # ── Stage 3 — Density classification ─────────────────────────────────────
    print("[3/5] Density classification...")
    density_class, dt_conf = _detect_density(blobs, font_size, width, height, debug)
    label = _DENSITY_LABELS[density_class]
    print(f"      → class {density_class} ({label})  conf={dt_conf:.0%}")

    # ── Stage 3b — Line/frame filtering ──────────────────────────────────────
    filter_res = filter_line_blobs(blobs, width, height, font_size)
    blobs      = filter_res["clean_blobs"]
    rejected   = filter_res["rejected_blobs"]
    print(f"      blobs rejected={len(rejected)}")

    # ── Stage 4 — Region grouping + standalone equations ─────────────────────
    print("[4/5] Standalone equation classification...")
    regions = group_blobs_into_regions(
        blobs, font_size,
        h_gap_factor=2.3,
        line_v_factor=0.6,
        para_v_factor=None,
    )

    eq_results_p1 = detect_standalone_equations(
        regions, font_size, height,
        density_class=density_class,
        top_margin=0.05,
        debug=debug,
    )

    eq_boxes_set = {d["box"] for d in eq_results_p1}
    text_boxes   = [
        (r["x1"], r["y1"], r["x2"], r["y2"])
        for r in regions
        if (r["x1"], r["y1"], r["x2"], r["y2"]) not in eq_boxes_set
    ]
    print(f"      standalone={len(eq_results_p1)}  text_regions={len(text_boxes)}")

    # ── Stage 5 — Inline equations (MEDIUM + DENSE only) ─────────────────────
    eq_results_p2 = []
    if density_class >= 1:
        print(f"[5/5] Inline equation detection (class {density_class} — {label})...")
        text_regions_with_blobs = [
            r for r in regions
            if (r["x1"], r["y1"], r["x2"], r["y2"]) not in eq_boxes_set
        ]
        eq_results_p2 = detect_inline_equations(
            text_regions_with_blobs,
            font_size,
            score_threshold=inline_score_threshold,
            delta_threshold=inline_delta_threshold,
            gap_factor=inline_gap_factor,
            max_cluster_size=inline_max_cluster_size,
            sentence_min_n=inline_sentence_min_n,
            tiny_height_ratio=inline_tiny_height_ratio,
            frac_width_ratio=inline_frac_width_ratio,
            frac_height_ratio=inline_frac_height_ratio,
            tall_height_ratio=inline_tall_height_ratio,
            baseline_max=inline_baseline_max,
            debug=debug,
        )
        print(f"      inline={len(eq_results_p2)}")
    else:
        print("[5/5] Inline pass skipped (SPARSE — no inline scan)")

    # ── Summary ───────────────────────────────────────────────────────────────
    eq_results = eq_results_p1 + eq_results_p2
    print(f"\n── Results ─────────────────────────────────────────")
    print(f"   Density class   : {density_class}  ({label})")
    print(f"   Text regions    : {len(text_boxes)}")
    print(f"   Standalone (c0) : {len(eq_results_p1)}")
    print(f"   Inline     (c1) : {len(eq_results_p2)}")
    print(f"   Total equations : {len(eq_results)}")
    print(f"────────────────────────────────────────────────────\n")

    return gray, binary, blobs, font_size, text_boxes, eq_results