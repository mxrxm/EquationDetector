"""
pipeline/crop_equations.py
──────────────────────────
Crops detected equation regions from a grayscale 2-D list (pure Python,
no NumPy) and returns PIL Images ready for saving or display.

Public API
----------
crop_standalone(gray, eq_results, padding=10)
    → list of dicts:
        {
          "index":      int,          # 1-based, sorted top-to-bottom
          "box":        (x1,y1,x2,y2),
          "confidence": float,
          "image":      PIL.Image,    # mode "L" (grayscale)
        }

crop_single(gray, box, padding=10)
    → PIL.Image  (mode "L")

Notes
-----
- gray is the raw 2-D list[list[int]] produced by run_cca_pipeline().
  Values are 0-255 integers.
- PIL (Pillow) is the only dependency — same as the rest of the project.
- Padding is clamped to image boundaries so border boxes never raise.
"""

from __future__ import annotations
from PIL import Image


def crop_single(gray: list[list[int]], box: tuple, padding: int = 10) -> Image.Image:
    """
    Crop one bounding box from a grayscale 2-D list.

    Parameters
    ----------
    gray    : 2-D list of int (0-255), shape [height][width]
    box     : (x1, y1, x2, y2) pixel coordinates
    padding : extra pixels to add on each side (clamped to image bounds)

    Returns
    -------
    PIL.Image in mode "L"
    """
    x1, y1, x2, y2 = box
    img_h = len(gray)
    img_w = len(gray[0]) if img_h > 0 else 0

    # Clamp with padding
    cx1 = max(0, x1 - padding)
    cy1 = max(0, y1 - padding)
    cx2 = min(img_w, x2 + padding)
    cy2 = min(img_h, y2 + padding)

    crop_w = cx2 - cx1
    crop_h = cy2 - cy1

    if crop_w <= 0 or crop_h <= 0:
        # Return a 1×1 blank image rather than crashing
        return Image.new("L", (1, 1), color=255)

    # Build flat bytes row-by-row — correct input for Image.frombytes
    raw = bytearray(crop_h * crop_w)
    for row_i, gy in enumerate(range(cy1, cy2)):
        row = gray[gy]
        for col_i, gx in enumerate(range(cx1, cx2)):
            raw[row_i * crop_w + col_i] = row[gx]

    return Image.frombytes("L", (crop_w, crop_h), bytes(raw))


def crop_standalone(
    gray: list[list[int]],
    eq_results: list[dict],
    padding: int = 10,
) -> list[dict]:
    """
    Crop every standalone (class 0) equation detected by the pipeline.

    Parameters
    ----------
    gray       : 2-D list[list[int]] from run_cca_pipeline()
    eq_results : list of detection dicts {"box", "confidence", "class"}
    padding    : pixels to pad around each bounding box

    Returns
    -------
    List of dicts sorted by vertical position (top → bottom):
        {
          "index":      int,           # 1-based
          "box":        (x1,y1,x2,y2),
          "confidence": float,
          "image":      PIL.Image,     # mode "L"
        }
    """
    standalone = [d for d in eq_results if d.get("class") == 0]
    # Sort top-to-bottom by y1 of bounding box
    standalone_sorted = sorted(standalone, key=lambda d: d["box"][1])

    results = []
    for idx, det in enumerate(standalone_sorted, start=1):
        pil_img = crop_single(gray, det["box"], padding=padding)
        results.append(
            {
                "index":      idx,
                "box":        det["box"],
                "confidence": det["confidence"],
                "image":      pil_img,
            }
        )
    return results