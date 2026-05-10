
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
    gray       : 2-D list[int]   grayscale pixel values (0-255)
    binary     : 2-D list[int]   binarized image (1=ink, 0=background)
    blobs      : list[dict]      every ink blob with shape features
    font_size  : int             estimated body-text glyph height in px
    text_boxes : list[tuple]     (x1,y1,x2,y2) of regions classified as text
    eq_results : list[dict]      {box, confidence, class: 0}
                                 class 0 = standalone / display equation only
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from .blob_detector import BlobDocumentTypeDetector
from .frame_line_detector import filter_line_blobs
from .region_grouping import group_blobs_into_regions
from .preprocessing import _dilate, _erode, preprocess
from .blob_analysis import run_blob_analysis
from .standalone_equations import detect_standalone_equations



def _detect_density(blobs, font_size, width, height, debug):
    """Returns (density_class: int, confidence: float)."""
    detector = BlobDocumentTypeDetector()

    result = detector.detect(
        blobs=blobs,
        img_width=width,
        img_height=height,
        font_size=font_size,
        debug=debug,
    )
    return result.density_class, result.confidence

_DENSITY_LABELS = {0: "SPARSE", 1: "MEDIUM", 2: "DENSE"}


# ════════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════════

def run_cca_pipeline(image_path,
                     detector_mode="blob",
                     debug=False):
    """
    Run the standalone-equation detection pipeline on one document image.

    Parameters
    ----------
    image_path    : str   path to any PIL-readable image
    detector_mode : str   "blob" (default)
    debug         : bool  print per-region scores to stdout

    Returns
    -------
    gray, binary, blobs, font_size, text_boxes, eq_results
    """

    # ── Stage 1 — Preprocessing ───────────────────────────────────────────────
    print(f"[1/4] Preprocessing: {os.path.basename(image_path)}")
    pre    = preprocess(image_path)
    gray   = pre["gray"]
    binary = pre["binary"]
    width  = pre["width"]
    height = pre["height"]
    print(f"      {width}×{height}px")

    # ── Stage 2 — Blob analysis ───────────────────────────────────────────────
    print("[2/4] Blob analysis...")
    blob_res  = run_blob_analysis(binary)
    blobs     = blob_res["blobs"]
    font_size = blob_res["font_size"]
    print(f"      blobs={len(blobs)}  font_size={font_size}px")

    # ── Stage 3 — Density classification + line filtering ────────────────────
    print("[3/4] Density classification...")
    density_class, dt_conf = _detect_density(
        blobs, font_size, width, height, debug
    )
    label = _DENSITY_LABELS[density_class]
    print(f"      → class {density_class} ({label})  conf={dt_conf:.0%}")

    filter_res = filter_line_blobs(blobs, width, height, font_size,line_span_factor=0.10)
    blobs      = filter_res["clean_blobs"]
    print(f"      blobs rejected={len(filter_res['rejected_blobs'])}")
    

    line_v_factor = {0: 0.8, 1: 0.7, 2: 0.5}.get(density_class)
    h_gap_factor = {0: 2.4, 1:2.2 , 2: 1.8}.get(density_class)
    # ── Stage 4 — Region grouping + standalone equation detection ─────────────
    print("[4/4] Standalone equation classification...")
    regions = group_blobs_into_regions(
        blobs, font_size,
        h_gap_factor=h_gap_factor,
        line_v_factor=line_v_factor,
        para_v_factor=None,
        min_blobs_per_region=1,
    )

    eq_results = detect_standalone_equations(
        regions, font_size, height,
        density_class=density_class,
        img_width=width,
        top_margin=0.05,
        debug=debug,
    )

    text_boxes = [
        (r["x1"], r["y1"], r["x2"], r["y2"])
        for r in regions
        if (r["x1"], r["y1"], r["x2"], r["y2"]) not in {d["box"] for d in eq_results}
    ]
    print(f"      standalone={len(eq_results)}  text_regions={len(text_boxes)}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n── Results ─────────────────────────────────────────")
    print(f"   Density class   : {density_class}  ({label})")
    print(f"   Text regions    : {len(text_boxes)}")
    print(f"   Standalone (c0) : {len(eq_results)}")
    print(f"────────────────────────────────────────────────────\n")

    return gray, binary, blobs, font_size, text_boxes, eq_results