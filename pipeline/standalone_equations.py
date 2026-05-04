import math


from pipeline.blob_analysis import run_blob_analysis
import region_grouping
import preprocessing



# ─────────────────────────────────────────
# Stage 6 — Classify regions → standalone equations only
# Returns list of dicts {box, confidence, class=0}
# ─────────────────────────────────────────

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

        tall_blobs    = sum(1 for b in blobs if b["height"] > font_size * 1.8)
        wide_blobs    = sum(1 for b in blobs if b["width"] > font_size * 4.0
                            and b["height"] < font_size * 0.5)
        outlier_ratio = (tall_blobs + wide_blobs) / len(blobs)

        height_ratio  = h / font_size
        region_ar     = w / h if h > 0 else 0

        centers      = [b["center_r"] for b in blobs]
        center_span  = (max(centers) - min(centers)) / font_size

        body_like    = sum(1 for b in blobs
                           if font_size * 0.6 <= b["height"] <= font_size * 1.4)
        body_ratio   = body_like / len(blobs)

        region_center = (y1 + y2) / 2
        band_half     = font_size * 0.35
        band_like     = sum(1 for c in centers
                            if abs(c - region_center) <= band_half)
        band_ratio    = band_like / len(blobs)

        blob_area     = sum(b["area"] for b in blobs)
        area_ratio    = blob_area / max(1, w * h)

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

        # Penalties
        if cv_h < 0.2 and height_ratio < 1.3:         score -= 3
        if region_ar > 10 and h < font_size * 1.3:    score -= 4
        if center_span < 0.7:                          score -= 2
        if body_ratio > 0.7 and height_ratio < 1.6:   score -= 2
        if band_ratio > 0.7 and height_ratio < 1.6:   score -= 1
        if area_ratio > 0.35 and height_ratio > 2.5:  score -= 2

        # Mixed-structure bonus
        if cv_h > 0.7 and cv_ar > 0.6 and body_ratio < 0.4:
            score += 3

        # ── Hard guards → reject ────────────────────────────────────────
        if (region_ar > 6 and height_ratio < 1.5
                and center_span < 0.9 and body_ratio > 0.6):
            score = -99
        if (len(blobs) <= 12 and height_ratio < 1.7
                and center_span < 1.0 and body_ratio > 0.5):
            score = -99
        if (region_ar > 8 and cv_h < 0.5 and cv_ar < 0.5 and band_ratio > 0.6):
            score = -99
        if (height_ratio > 3.0 and cv_h < 0.45 and cv_ar < 1.75
                and outlier_ratio < 0.08 and body_ratio > 0.60):
            score = -99

        if debug:
            print(f"  ({x1},{y1})-({x2},{y2}) blobs={len(blobs):3d} "
                  f"cv_h={cv_h:.2f} outliers={outlier_ratio:.2f} "
                  f"h_ratio={height_ratio:.1f} ar={region_ar:.1f} "
                  f"score={score:+d} → {'EQ' if score >= 3 else 'TEXT'}")

        if score < 3:
            continue

        confidence = min(1.0, max(0.0, score / MAX_SCORE))

        # Low-confidence detections are likely text misclassified
        if confidence <= 0.3:
            continue

        results.append({
            "box":        (x1, y1, x2, y2),
            "confidence": round(confidence, 3),
            "class":      0,
        })

    return results


# # ─────────────────────────────────────────
# # Public entry point
# # ─────────────────────────────────────────

# def detect(image_path, debug=False):
#     """
#     Run the standalone-equation detector on a single image.

#     Parameters
#     ----------
#     image_path : str   path to any PIL-readable image
#     debug      : bool  print per-region scoring details

#     Returns
#     -------
#     gray        : 2-D list of int (grayscale pixel values)
#     detections  : list of dicts {box:(x1,y1,x2,y2), confidence, class=0}
#     """
#     result    = preprocessing.preprocess(image_path)
#     gray      = result["gray"]
#     binary    = result["binary"]
#     width     = result["width"]
#     height    = result["height"]

#     blob_result = run_blob_analysis(binary)
#     blobs     = blob_result["blobs"]
#     font_size = blob_result["font_size"]

#     regions =region_grouping(blobs, font_size,
#                               h_gap_factor=2.3, v_gap_factor=1.2)
#     detections = detect_standalone_equations(
#         regions, font_size, height, top_margin=0.05, debug=debug
#     )

#     print(f"Standalone equations detected: {len(detections)}")
#     return gray, detections


# # ─────────────────────────────────────────
# Optional: save annotated image
# ─────────────────────────────────────────

# def save_result(gray, detections, out_path="standalone_detections.png"):
#     fig, ax = plt.subplots(figsize=(12, 16))
#     ax.imshow(gray, cmap="gray", vmin=0, vmax=255)

#     for det in detections:
#         x1, y1, x2, y2 = det["box"]
#         conf = det["confidence"]
#         rect = patches.Rectangle(
#             (x1, y1), x2 - x1, y2 - y1,
#             linewidth=2, edgecolor="red",
#             facecolor="red", alpha=0.15
#         )
#         ax.add_patch(rect)
#         ax.text(x1 + 2, y1 - 3, f"{conf:.2f}",
#                 color="red", fontsize=7, fontweight="bold",
#                 verticalalignment="bottom")

#     ax.set_title(f"Standalone equations detected: {len(detections)}", fontsize=12)
#     ax.axis("off")
#     plt.tight_layout()
#     plt.savefig(out_path, dpi=150, bbox_inches="tight")
#     plt.close()
#     print(f"Saved: {out_path}")


# # ─────────────────────────────────────────
# # Batch runner
# # ─────────────────────────────────────────

# import os
# import csv
# import glob

# def run_batch(input_dir, output_dir, pattern="*.png", debug=False):
#     """
#     Run standalone equation detection on all images in input_dir.

#     For each image it produces:
#       - an annotated PNG  → output_dir/<stem>_detections.png
#       - a per-image CSV   → output_dir/<stem>_detections.csv

#     After all images it writes a summary CSV → output_dir/summary.csv
#     with one row per image: filename, num_detections, avg_confidence.

#     Parameters
#     ----------
#     input_dir  : str   folder that contains the images
#     output_dir : str   folder where results are written (created if missing)
#     pattern    : str   glob pattern for image files (default "*.png")
#     debug      : bool  pass-through to detect()
#     """
#     os.makedirs(output_dir, exist_ok=True)

#     image_paths = sorted(glob.glob(os.path.join(input_dir, pattern)))
#     if not image_paths:
#         print(f"No images matched '{pattern}' in '{input_dir}'")
#         return

#     print(f"Found {len(image_paths)} image(s) — starting batch...\n")

#     summary_rows = []

#     for idx, img_path in enumerate(image_paths, 1):
#         stem = os.path.splitext(os.path.basename(img_path))[0]
#         print(f"[{idx}/{len(image_paths)}] {stem}")

#         try:
#             gray, detections = detect(img_path, debug=debug)
#         except Exception as e:
#             print(f"  ERROR: {e}\n")
#             summary_rows.append({
#                 "filename":        os.path.basename(img_path),
#                 "num_detections":  "ERROR",
#                 "avg_confidence":  "ERROR",
#             })
#             continue

#         # Annotated image
#         out_img = os.path.join(output_dir, f"{stem}_detections.png")
#         save_result(gray, detections, out_path=out_img)

#         # Per-image CSV
#         out_csv = os.path.join(output_dir, f"{stem}_detections.csv")
#         with open(out_csv, "w", newline="") as f:
#             writer = csv.writer(f)
#             writer.writerow(["x1", "y1", "x2", "y2", "confidence"])
#             for det in detections:
#                 x1, y1, x2, y2 = det["box"]
#                 writer.writerow([x1, y1, x2, y2, det["confidence"]])
#         print(f"  CSV saved: {out_csv}\n")

#         avg_conf = (
#             round(sum(d["confidence"] for d in detections) / len(detections), 3)
#             if detections else 0.0
#         )
#         summary_rows.append({
#             "filename":       os.path.basename(img_path),
#             "num_detections": len(detections),
#             "avg_confidence": avg_conf,
#         })

#     # Summary CSV
#     summary_path = os.path.join(output_dir, "summary.csv")
#     with open(summary_path, "w", newline="") as f:
#         writer = csv.DictWriter(f, fieldnames=["filename",
#                                                 "num_detections",
#                                                 "avg_confidence"])
#         writer.writeheader()
#         writer.writerows(summary_rows)

#     total_eq = sum(
#         r["num_detections"] for r in summary_rows
#         if isinstance(r["num_detections"], int)
#     )
#     print(f"Batch done — {len(image_paths)} images | "
#           f"{total_eq} total detections")
#     print(f"Summary saved: {summary_path}")


# # ─────────────────────────────────────────
# # MAIN
# # ─────────────────────────────────────────

# if __name__ == "__main__":
#     INPUT_DIR  = "dataset/images"          # ← folder with your input images
#     OUTPUT_DIR = "results"         # ← folder for annotated PNGs + CSVs
#     PATTERN    = "*.jpeg"           # ← change to "*.jpg" or "*.png;*.jpg" etc.

#     run_batch(INPUT_DIR, OUTPUT_DIR, pattern=PATTERN, debug=False)