"""
test_pipeline.py
================
Quick sanity test for preprocessing.py and blob_analysis.py.

Usage
-----
    python test_pipeline.py path/to/your/image.jpg

What it checks
--------------
    preprocessing :
        - image loads without crash
        - gray  is a 2-D list of ints in [0, 255]
        - binary is a 2-D list of 0/1 values
        - skew_angle and was_stretched are reported
        - saves  debug_gray.png  and  debug_binary.png  next to the script

    blob_analysis :
        - blobs are found
        - font_size is a sane value
        - regions are formed
        - prints top-10 blobs sorted by area
        - prints top-10 regions sorted by blob_count
        - saves  debug_regions.png  (bounding boxes drawn on gray image)
"""

import sys
import os

# ── make sure modules are found even if run from a different cwd ──────────────
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from preprocessing import preprocess
from blob_analysis import run_blob_analysis
import blob_analysis
print("LOADED FROM:", blob_analysis.__file__)

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("[ERROR] Pillow is not installed.  Run:  pip install Pillow")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def save_gray(gray, path):
    h, w = len(gray), len(gray[0])
    img  = Image.new("L", (w, h))
    img.putdata([gray[r][c] for r in range(h) for c in range(w)])
    img.save(path)
    print(f"    saved → {path}")


def save_binary(binary, path):
    h, w = len(binary), len(binary[0])
    img  = Image.new("L", (w, h))
    img.putdata([binary[r][c] * 255 for r in range(h) for c in range(w)])
    img.save(path)
    print(f"    saved → {path}")


def save_regions(gray, blobs, regions, path):
    h, w = len(gray), len(gray[0])
    # Convert gray to RGB so we can draw coloured boxes
    base = Image.new("RGB", (w, h))
    base.putdata([(gray[r][c],) * 3 for r in range(h) for c in range(w)])
    draw = ImageDraw.Draw(base)

    # Draw blob bounding boxes in green
    for b in blobs:
        draw.rectangle([b["x1"], b["y1"], b["x2"], b["y2"]],
                       outline=(0, 200, 0))

    # Draw region bounding boxes in red
    for reg in regions:
        draw.rectangle([reg["x1"], reg["y1"], reg["x2"], reg["y2"]],
                       outline=(220, 30, 30), width=2)

    base.save(path)
    print(f"    saved → {path}")


def hr(title=""):
    print("\n" + "─" * 60)
    if title:
        print(f"  {title}")
        print("─" * 60)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage:  python test_pipeline.py  <image_path>")
        sys.exit(1)

    image_path = sys.argv[1]
    if not os.path.isfile(image_path):
        print(f"[ERROR] File not found: {image_path}")
        sys.exit(1)

    print(f"\nImage : {image_path}")

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 1 — preprocessing
    # ──────────────────────────────────────────────────────────────────────────
    hr("STAGE 1-2 : preprocessing")

    result = preprocess(image_path)

    gray   = result["gray"]
    binary = result["binary"]
    h      = result["height"]
    w      = result["width"]

    print(f"  dimensions       : {w} × {h}  (width × height)")
    # print(f"  skew_angle       : {result['skew_angle']:.2f}°"
    #       f"  {'(corrected)' if result['skew_angle'] != 0.0 else '(no correction)'}")
    print(f"  was_stretched    : {result['was_stretched']}"
          f"  {'(low contrast — histogram stretched)' if result['was_stretched'] else ''}")
    print(f"  global_threshold : {result['global_threshold']}")

    # ── spot-check gray ───────────────────────────────────────────────────────
    flat_gray = [gray[r][c] for r in range(h) for c in range(w)]
    assert all(0 <= v <= 255 for v in flat_gray),  "gray values out of [0,255]"
    print(f"  gray range       : [{min(flat_gray)}, {max(flat_gray)}]  ✓")

    # ── spot-check binary ─────────────────────────────────────────────────────
    flat_bin  = [binary[r][c] for r in range(h) for c in range(w)]
    assert all(v in (0, 1) for v in flat_bin),     "binary contains values other than 0/1"
    ink_pct   = 100 * sum(flat_bin) / len(flat_bin)
    print(f"  binary ink %     : {ink_pct:.2f}%  ✓")

    # ── save debug images ─────────────────────────────────────────────────────
    print("  debug images:")
    save_gray(gray,     "debug_gray.png")
    save_binary(binary, "debug_binary.png")

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 2 — blob analysis
    # ──────────────────────────────────────────────────────────────────────────
    hr("STAGE 3-5 : blob_analysis")

    blob_result = run_blob_analysis(binary)

    blobs     = blob_result["blobs"]
    font_size = blob_result["font_size"]
    regions   = blob_result["regions"]

    print(f"  total blobs      : {len(blobs)}")
    print(f"  font_size        : {font_size} px")
    print(f"  total regions    : {len(regions)}")

    assert len(blobs) > 0,   "No blobs found — check binary image"
    assert font_size  > 0,   "font_size must be positive"

    # ── top-10 blobs by area ──────────────────────────────────────────────────
    print("\n  Top 10 blobs by area:")
    print(f"  {'#':>3}  {'area':>6}  {'w':>5}  {'h':>5}  "
          f"{'fill':>5}  {'aspect':>6}  {'x1':>5}  {'y1':>5}")
    print("  " + "-" * 55)
    for i, b in enumerate(sorted(blobs, key=lambda x: -x["area"])[:10], 1):
        print(f"  {i:>3}  {b['area']:>6}  {b['width']:>5}  {b['height']:>5}  "
              f"{b['fill_ratio']:>5.2f}  {b['aspect_ratio']:>6.2f}  "
              f"{b['x1']:>5}  {b['y1']:>5}")

    # ── top-10 regions by blob_count ──────────────────────────────────────────
    print("\n  Top 10 regions by blob count:")
    print(f"  {'#':>3}  {'blobs':>6}  {'w':>6}  {'h':>6}  "
          f"{'density':>8}  {'x1':>6}  {'y1':>6}")
    print("  " + "-" * 55)
    for i, reg in enumerate(sorted(regions, key=lambda x: -x["blob_count"])[:10], 1):
        print(f"  {i:>3}  {reg['blob_count']:>6}  {reg['width']:>6}  "
              f"{reg['height']:>6}  {reg['density']:>8.4f}  "
              f"{reg['x1']:>6}  {reg['y1']:>6}")

    # ── save debug image ──────────────────────────────────────────────────────
    print("\n  debug image:")
    save_regions(gray, blobs, regions, "debug_regions.png")

    # ──────────────────────────────────────────────────────────────────────────
    hr("ALL TESTS PASSED")
    print()


if __name__ == "__main__":
    main()