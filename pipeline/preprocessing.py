# """
# preprocessing.py
# ================
# Stage 1 & 2 of the Equation Detector Pipeline.

# Pure Python implementation — Pillow used ONLY for image I/O.
# No NumPy, no OpenCV, no SciPy.

# Pipeline
# --------
#     1. Mode normalisation     — RGBA / P / L / 1  →  RGB
#     2. Max-dim resize         — clamp large images to prevent OOM
#     3. Grayscale conversion   — weighted luminance  (BT.601)
#     4. Contrast normalisation — histogram stretch   (auto, only if needed)
#     5. Deskew                 — projection-profile rotation (auto, only if needed)
#     6. Gaussian blur          — separable 1-D passes (radius auto or caller-set)
#     7. Adaptive tiled Otsu    — per-tile threshold + bilinear interpolation
#     8. Morphological opening  — erosion → dilation  (speckle removal)

# Public API
# ----------
#     result = preprocess(path, max_dim=2000, tile_size=128, blur_radius=None)

#     result["gray"]             — 2-D list[list[int]]   pixel values 0-255
#     result["binary"]           — 2-D list[list[int]]   0 = background, 1 = text
#     result["width"]            — int
#     result["height"]           — int
#     result["global_threshold"] — int    global Otsu value (0-255)
#     result["tile_thresholds"]  — 2-D list[list[int]]   per-tile Otsu values
#     result["skew_angle"]       — float  degrees applied  (0.0 if none)
#     result["was_stretched"]    — bool   True if contrast stretch was applied
# """

# import math
# from PIL import Image


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 1 — Mode normalisation + loading
# # ═══════════════════════════════════════════════════════════════════════════════

# def _load_normalised(path):
#     """
#     Open any PIL-readable image, flatten transparency if present,
#     and return a plain RGB PIL Image.
#     """
#     img  = Image.open(path)
#     mode = img.mode

#     if mode in ("RGBA", "LA"):
#         # paste onto white background to flatten alpha
#         bg = Image.new("RGB", img.size, (255, 255, 255))
#         if mode == "RGBA":
#             bg.paste(img, mask=img.split()[3])
#         else:
#             bg.paste(img.convert("RGB"))
#         img = bg

#     elif mode == "P":
#         # palette → may have transparency info
#         img = img.convert("RGBA").convert("RGB") \
#             if "transparency" in img.info else img.convert("RGB")

#     elif mode == "1":
#         img = img.convert("L").convert("RGB")

#     elif mode == "L":
#         img = img.convert("RGB")

#     elif mode == "RGB":
#         pass

#     else:
#         img = img.convert("RGB")         # safe fallback

#     return img


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 2 — Max-dim resize
# # ═══════════════════════════════════════════════════════════════════════════════

# def _resize_if_needed(img, max_dim):
#     """
#     Downscale img so its larger dimension does not exceed max_dim.
#     Returns (img, scale_factor).  scale_factor == 1.0 means no change.
#     """
#     if max_dim is None:
#         return img, 1.0

#     w, h = img.size
#     if max(w, h) <= max_dim:
#         return img, 1.0

#     scale = max_dim / max(w, h)
#     new_w = max(1, int(w * scale))
#     new_h = max(1, int(h * scale))
#     return img.resize((new_w, new_h), Image.LANCZOS), scale


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 3 — Grayscale conversion
# # ═══════════════════════════════════════════════════════════════════════════════

# def _to_grayscale(img):
#     """
#     Convert an RGB PIL Image to a 2-D list[list[int]] (0-255)
#     using the BT.601 luminance formula:  Y = 0.299R + 0.587G + 0.114B
#     """
#     w, h   = img.size
#     pixels = list(img.getdata())
#     gray   = []
#     for r in range(h):
#         row = []
#         for c in range(w):
#             R, G, B  = pixels[r * w + c]
#             gray_val = int(0.299 * R + 0.587 * G + 0.114 * B)
#             row.append(gray_val)
#         gray.append(row)
#     return gray


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 4 — Contrast normalisation  (histogram stretch)
# # ═══════════════════════════════════════════════════════════════════════════════

# def _needs_stretch(gray, low_contrast_threshold=80):
#     """
#     Return True if the dynamic range of the image is below
#     low_contrast_threshold  (faded scan / washed-out photo).
#     Uses the 2nd and 98th percentile to ignore extreme outliers.
#     """
#     h, w   = len(gray), len(gray[0])
#     flat   = sorted(gray[r][c] for r in range(h) for c in range(w))
#     n      = len(flat)
#     p2     = flat[int(0.02 * n)]
#     p98    = flat[int(0.98 * n)]
#     return (p98 - p2) < low_contrast_threshold


# def _stretch_contrast(gray):
#     """
#     Linear histogram stretch: map [p2, p98] → [0, 255].
#     Pixels outside that range are clamped.
#     Returns a new 2-D list[list[int]].
#     """
#     h, w = len(gray), len(gray[0])
#     flat = sorted(gray[r][c] for r in range(h) for c in range(w))
#     n    = len(flat)
#     lo   = flat[int(0.02 * n)]
#     hi   = flat[int(0.98 * n)]

#     if hi == lo:            # degenerate image (solid colour)
#         return [row[:] for row in gray]

#     scale  = 255.0 / (hi - lo)
#     result = []
#     for r in range(h):
#         row = []
#         for c in range(w):
#             v = int((gray[r][c] - lo) * scale)
#             row.append(max(0, min(255, v)))
#         result.append(row)
#     return result


# # # ═══════════════════════════════════════════════════════════════════════════════
# # # STEP 5 — Deskew  (projection-profile method)
# # # ═══════════════════════════════════════════════════════════════════════════════

# # def _quick_binarize(gray):
# #     """
# #     Fast single-pass global Otsu binarize — used only internally for deskew.
# #     Returns a flat list of 0/1 values (row-major).
# #     """
# #     h, w      = len(gray), len(gray[0])
# #     flat      = [gray[r][c] for r in range(h) for c in range(w)]
# #     histogram = [0] * 256
# #     for v in flat:
# #         histogram[v] += 1
# #     total     = h * w
# #     best_t    = 128
# #     best_var  = -1.0
# #     weight_bg = 0
# #     sum_bg    = 0
# #     total_sum = sum(i * histogram[i] for i in range(256))
# #     for t in range(256):
# #         weight_bg += histogram[t]
# #         if weight_bg == 0:
# #             continue
# #         weight_fg = total - weight_bg
# #         if weight_fg == 0:
# #             break
# #         sum_bg   += t * histogram[t]
# #         mean_bg   = sum_bg / weight_bg
# #         mean_fg   = (total_sum - sum_bg) / weight_fg
# #         var       = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
# #         if var > best_var:
# #             best_var = var
# #             best_t   = t
# #     return [1 if flat[i] < best_t else 0 for i in range(total)], best_t


# # def _horizontal_projection(binary_flat, width, height, angle_deg):
# #     """
# #     Rotate binary_flat by angle_deg (small angle approximation via shear),
# #     then compute the horizontal projection profile variance.
# #     Higher variance → text lines are more horizontal → better alignment.
# #     """
# #     rad   = math.radians(angle_deg)
# #     tan_a = math.tan(rad)
# #     rows  = [0] * height

# #     for r in range(height):
# #         for c in range(width):
# #             # shear: shift column by tan(angle) * row
# #             nc = c + int(r * tan_a)
# #             if 0 <= nc < width:
# #                 rows[r] += binary_flat[r * width + nc]

# #     mean = sum(rows) / height
# #     var  = sum((x - mean) ** 2 for x in rows) / height
# #     return var


# # def _detect_skew(gray, angle_range=5, angle_step=0.5, min_angle=1.0):
# #     """
# #     Search angles in [-angle_range, +angle_range] step angle_step degrees.
# #     Return the angle with the highest horizontal projection variance.
# #     Returns 0.0 if the best angle is within min_angle of 0 (no correction needed).
# #     """
# #     h, w          = len(gray), len(gray[0])
# #     binary_flat, _ = _quick_binarize(gray)

# #     best_angle = 0.0
# #     best_var   = -1.0

# #     angle = -angle_range
# #     while angle <= angle_range:
# #         var = _horizontal_projection(binary_flat, w, h, angle)
# #         if var > best_var:
# #             best_var   = var
# #             best_angle = angle
# #         angle = round(angle + angle_step, 6)

# #     if abs(best_angle) < min_angle:
# #         return 0.0
# #     return best_angle


# # def _rotate_gray(gray, angle_deg):
# #     """
# #     Rotate the grayscale 2-D list by angle_deg using bilinear interpolation.
# #     Background fill is 255 (white).
# #     Returns a new 2-D list of the same dimensions.
# #     """
# #     if angle_deg == 0.0:
# #         return gray

# #     h, w  = len(gray), len(gray[0])
# #     rad   = math.radians(-angle_deg)   # negative → correct direction
# #     cos_a = math.cos(rad)
# #     sin_a = math.sin(rad)
# #     cx    = w / 2.0
# #     cy    = h / 2.0

# #     result = []
# #     for r in range(h):
# #         row = []
# #         for c in range(w):
# #             # map destination pixel back to source
# #             dx  = c - cx
# #             dy  = r - cy
# #             src_c = cos_a * dx - sin_a * dy + cx
# #             src_r = sin_a * dx + cos_a * dy + cy

# #             # bilinear interpolation
# #             r0, c0 = int(math.floor(src_r)), int(math.floor(src_c))
# #             r1, c1 = r0 + 1, c0 + 1
# #             dr, dc  = src_r - r0, src_c - c0

# #             def safe(rr, cc):
# #                 if 0 <= rr < h and 0 <= cc < w:
# #                     return gray[rr][cc]
# #                 return 255   # white background

# #             val = (safe(r0, c0) * (1 - dr) * (1 - dc) +
# #                    safe(r0, c1) * (1 - dr) *      dc  +
# #                    safe(r1, c0) *      dr  * (1 - dc) +
# #                    safe(r1, c1) *      dr  *      dc)
# #             row.append(int(round(val)))
# #         result.append(row)
# #     return result


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 6 — Gaussian blur  (separable 1-D passes)
# # ═══════════════════════════════════════════════════════════════════════════════

# def _gaussian_kernel_1d(radius):
#     """
#     Build a normalised 1-D Gaussian kernel of half-width radius.
#     sigma = radius / 2  (standard rule of thumb).
#     """
#     if radius == 0:
#         return [1.0]
#     sigma  = max(radius / 2.0, 0.5)
#     size   = 2 * radius + 1
#     kernel = [math.exp(-((i - radius) ** 2) / (2 * sigma ** 2))
#               for i in range(size)]
#     total  = sum(kernel)
#     return [k / total for k in kernel]


# def _convolve_horizontal(image, kernel):
#     h, w   = len(image), len(image[0])
#     radius = len(kernel) // 2
#     out    = []
#     for r in range(h):
#         row = []
#         for c in range(w):
#             acc = 0.0
#             for ki, kv in enumerate(kernel):
#                 cc  = min(max(c + ki - radius, 0), w - 1)
#                 acc += image[r][cc] * kv
#             row.append(acc)
#         out.append(row)
#     return out


# def _convolve_vertical(image, kernel):
#     h, w   = len(image), len(image[0])
#     radius = len(kernel) // 2
#     out    = [[0.0] * w for _ in range(h)]
#     for r in range(h):
#         for c in range(w):
#             acc = 0.0
#             for ki, kv in enumerate(kernel):
#                 rr  = min(max(r + ki - radius, 0), h - 1)
#                 acc += image[rr][c] * kv
#             out[r][c] = acc
#     return out


# def _gaussian_blur(gray, radius):
#     """Full separable Gaussian blur. Returns 2-D list[list[int]]."""
#     if radius == 0:
#         return gray
#     kernel  = _gaussian_kernel_1d(radius)
#     tmp     = _convolve_horizontal(gray, kernel)
#     blurred = _convolve_vertical(tmp, kernel)
#     h, w    = len(blurred), len(blurred[0])
#     return [[int(round(blurred[r][c])) for c in range(w)] for r in range(h)]


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 7 — Adaptive tiled Otsu binarization
# # ═══════════════════════════════════════════════════════════════════════════════

# def _otsu_on_patch(flat_pixels):
#     """
#     Compute Otsu threshold on a flat list of ints (0-255).
#     Returns threshold t:  pixels < t  →  foreground (ink).
#     """
#     total = len(flat_pixels)
#     if total == 0:
#         return 128

#     histogram = [0] * 256
#     for v in flat_pixels:
#         histogram[v] += 1

#     best_t    = 128
#     best_var  = -1.0
#     weight_bg = 0
#     sum_bg    = 0
#     total_sum = sum(i * histogram[i] for i in range(256))

#     for t in range(256):
#         weight_bg += histogram[t]
#         if weight_bg == 0:
#             continue
#         weight_fg = total - weight_bg
#         if weight_fg == 0:
#             break
#         sum_bg   += t * histogram[t]
#         mean_bg   = sum_bg / weight_bg
#         mean_fg   = (total_sum - sum_bg) / weight_fg
#         var       = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
#         if var > best_var:
#             best_var = var
#             best_t   = t

#     return best_t


# def _compute_tile_thresholds(gray, tile_size):
#     """
#     Divide the image into tiles of tile_size × tile_size.
#     Return a 2-D list tile_thresh[tr][tc] of Otsu values.
#     """
#     h, w   = len(gray), len(gray[0])
#     n_rows = max(1, (h + tile_size - 1) // tile_size)
#     n_cols = max(1, (w + tile_size - 1) // tile_size)

#     tile_thresh = []
#     for tr in range(n_rows):
#         row_t = []
#         r0 = tr * tile_size
#         r1 = min(r0 + tile_size, h)
#         for tc in range(n_cols):
#             c0    = tc * tile_size
#             c1    = min(c0 + tile_size, w)
#             patch = [gray[r][c] for r in range(r0, r1) for c in range(c0, c1)]
#             row_t.append(_otsu_on_patch(patch))
#         tile_thresh.append(row_t)

#     return tile_thresh


# def _bilinear_interpolate_thresholds(tile_thresh, width, height, tile_size):
#     """
#     Bilinear-interpolate the coarse tile_thresh grid back to full resolution.
#     Returns a 2-D list thresh_map[r][c] (float).
#     """
#     n_rows = len(tile_thresh)
#     n_cols = len(tile_thresh[0])

#     thresh_map = []
#     for r in range(height):
#         row = []
#         # tile-space fractional position of pixel centre
#         tf = (r + 0.5) / tile_size - 0.5
#         tr0 = max(0, min(n_rows - 2, int(math.floor(tf))))
#         tr1 = tr0 + 1 if tr0 + 1 < n_rows else tr0
#         dr  = tf - tr0

#         for c in range(width):
#             cf  = (c + 0.5) / tile_size - 0.5
#             tc0 = max(0, min(n_cols - 2, int(math.floor(cf))))
#             tc1 = tc0 + 1 if tc0 + 1 < n_cols else tc0
#             dc  = cf - tc0

#             t00 = tile_thresh[tr0][tc0]
#             t01 = tile_thresh[tr0][tc1]
#             t10 = tile_thresh[tr1][tc0]
#             t11 = tile_thresh[tr1][tc1]

#             val = (t00 * (1 - dr) * (1 - dc) +
#                    t01 * (1 - dr) *      dc  +
#                    t10 *      dr  * (1 - dc) +
#                    t11 *      dr  *      dc)
#             row.append(val)
#         thresh_map.append(row)

#     return thresh_map


# def _adaptive_binarize(gray, tile_size):
#     """
#     Binarize using per-pixel interpolated adaptive threshold.
#     Returns:
#         binary        — 2-D list[list[int]]  0=background, 1=text
#         tile_thresh   — 2-D list[list[int]]  raw tile Otsu values
#         global_thresh — int                  single global Otsu value
#     """
#     h, w = len(gray), len(gray[0])

#     # Global threshold (kept for diagnostics)
#     flat          = [gray[r][c] for r in range(h) for c in range(w)]
#     global_thresh = _otsu_on_patch(flat)

#     # Tile thresholds + interpolated map
#     tile_thresh = _compute_tile_thresholds(gray, tile_size)
#     thresh_map  = _bilinear_interpolate_thresholds(tile_thresh, w, h, tile_size)

#     binary = [[1 if gray[r][c] < thresh_map[r][c] else 0
#                for c in range(w)] for r in range(h)]

#     return binary, tile_thresh, global_thresh


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 8 — Morphological opening  (erosion → dilation)
# # ═══════════════════════════════════════════════════════════════════════════════

# def _erode(binary):
#     """
#     3×3 erosion on a binary image (text=1, bg=0).
#     A pixel stays 1 only if ALL 8-neighbours and itself are 1.
#     """
#     h, w  = len(binary), len(binary[0])
#     out   = [[0] * w for _ in range(h)]
#     for r in range(1, h - 1):
#         for c in range(1, w - 1):
#             if (binary[r][c] == 1 and
#                     binary[r-1][c-1] and binary[r-1][c] and binary[r-1][c+1] and
#                     binary[r  ][c-1] and                    binary[r  ][c+1] and
#                     binary[r+1][c-1] and binary[r+1][c] and binary[r+1][c+1]):
#                 out[r][c] = 1
#     return out


# def _dilate(binary):
#     """
#     3×3 dilation on a binary image.
#     A pixel becomes 1 if ANY of its 8-neighbours or itself is 1.
#     """
#     h, w  = len(binary), len(binary[0])
#     out   = [[0] * w for _ in range(h)]
#     for r in range(1, h - 1):
#         for c in range(1, w - 1):
#             if (binary[r][c] or
#                     binary[r-1][c-1] or binary[r-1][c] or binary[r-1][c+1] or
#                     binary[r  ][c-1] or                   binary[r  ][c+1] or
#                     binary[r+1][c-1] or binary[r+1][c] or binary[r+1][c+1]):
#                 out[r][c] = 1
#     return out


# def _morphological_opening(binary):
#     """
#     Opening = erosion followed by dilation.
#     Removes isolated speckle pixels while preserving real strokes.
#     """
#     return _dilate(_erode(binary))


# # ═══════════════════════════════════════════════════════════════════════════════
# # PUBLIC ENTRY POINT
# # ═══════════════════════════════════════════════════════════════════════════════

# def preprocess(path, max_dim=2000, tile_size=128, blur_radius=None):
#     """
#     Run the full preprocessing pipeline on a single image.

#     Parameters
#     ----------
#     path        : str   path to any PIL-readable image
#     max_dim     : int   clamp largest dimension to this value (None = no resize)
#     tile_size   : int   tile side-length for adaptive Otsu (pixels)
#     blur_radius : int   Gaussian blur half-width; None = auto (1 for digital, 2 for scanned)

#     Returns
#     -------
#     dict with keys:
#         gray             — 2-D list[list[int]]   grayscale values 0-255
#         binary           — 2-D list[list[int]]   0=background, 1=text (after opening)
#         width            — int
#         height           — int
#         global_threshold — int
#         tile_thresholds  — 2-D list[list[int]]
#         skew_angle       — float   degrees corrected (0.0 = no correction)
#         was_stretched    — bool    True if contrast stretch was applied
#     """

#     # ── Step 1: Load + normalise mode ────────────────────────────────────────
#     img = _load_normalised(path)

#     # ── Step 2: Resize if needed ─────────────────────────────────────────────
#     img, _scale = _resize_if_needed(img, max_dim)

#     # ── Step 3: Grayscale conversion ─────────────────────────────────────────
#     gray = _to_grayscale(img)
#     height = len(gray)
#     width  = len(gray[0])

#     # ── Step 4: Contrast normalisation (auto-detect) ─────────────────────────
#     was_stretched = False
#     if _needs_stretch(gray):
#         gray          = _stretch_contrast(gray)
#         was_stretched = True

#     # # ── Step 5: Deskew (auto-detect) ─────────────────────────────────────────
#     # skew_angle = _detect_skew(gray)
#     # if skew_angle != 0.0:
#     #     gray = _rotate_gray(gray, skew_angle)

#     # ── Step 6: Gaussian blur ─────────────────────────────────────────────────
#     # Auto radius: scanned/low-contrast images get radius=2, clean digital get radius=1
#     if blur_radius is None:
#         blur_radius = 2 if was_stretched else 1
#     gray_blurred = _gaussian_blur(gray, blur_radius)

#     # ── Step 7: Adaptive tiled Otsu binarization ─────────────────────────────
#     binary, tile_thresholds, global_threshold = _adaptive_binarize(
#         gray_blurred, tile_size
#     )

#     # ── Step 8: Morphological opening (speckle removal) ──────────────────────
#     binary = _morphological_opening(binary)

#     return {
#         "gray":             gray,
#         "binary":           binary,
#         "width":            width,
#         "height":           height,
#         "global_threshold": global_threshold,
#         "tile_thresholds":  tile_thresholds,
#         # "skew_angle":       skew_angle,
#         "was_stretched":    was_stretched,
#     }
"""Image preprocessing utilities: load_grayscale, binarize."""
from PIL import Image
import math

def load_grayscale(image_path):
    """Load an image and convert to grayscale."""
    img = Image.open(image_path).convert("RGB")
    width, height = img.size
    pixels = list(img.getdata())
    gray = []
    for r in range(height):
        row = []
        for c in range(width):
            R, G, B = pixels[r * width + c]
            ##
            gray_val = int(0.299 * R + 0.587 * G + 0.114 * B)
            row.append(gray_val)
        gray.append(row)
    return gray, width, height

# ─────────────────────────────────────────
# STAGE 2 — Binarize (Otsu, inverted)
# text pixels = 1, background = 0
# ─────────────────────────────────────────

def binarize(image):
    """Binarize a grayscale image."""

    h, w  = len(image), len(image[0])
    flat  = [image[r][c] for r in range(h) for c in range(w)]
    total = h * w

    max_val   = max(flat) or 1
    histogram = [0] * 256
    for val in flat:
        histogram[int(val * 255 / max_val)] += 1

    best_t    = 0
    best_var  = -1.0
    weight_bg = 0
    sum_bg    = 0
    total_sum = sum(i * histogram[i] for i in range(256))

    for t in range(256):
        weight_bg += histogram[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg   += t * histogram[t]
        mean_bg   = sum_bg / weight_bg
        mean_fg   = (total_sum - sum_bg) / weight_fg
        variance  = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if variance > best_var:
            best_var = variance
            best_t   = t

    pixel_t = best_t * max_val / 255
    return [[1 if image[r][c] < pixel_t else 0
             for c in range(w)] for r in range(h)]

def preprocess(path):
    """
    Run the full preprocessing pipeline on a single image.

    Parameters
    ----------
    path        : str   path to any PIL-readable image

    Returns
    -------
    dict with keys:
        gray             — 2-D list[list[int]]   grayscale values 0-255
        binary           — 2-D list[list[int]]   0=background, 1=text (after opening)
        width            — int
        height           — int
    """


    gray,width,height  = load_grayscale(path)


    binary = binarize(gray)

    return {
        "gray":             gray,
        "binary":           binary,
        "width":            width,
        "height":           height,
    }