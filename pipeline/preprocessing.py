
# """
# preprocessing.py  [merged]
# ================
# Stages 1 & 2 of the Equation Detector Pipeline.

# Pure Python — Pillow used ONLY for image I/O.

# Merge notes
# -----------
# • API:            new flags-based API kept: gaussian_noise / negative_noise / unconnected
# • Binarization:   upgraded to ADAPTIVE TILED OTSU from original v1 (better than global
#                   Otsu for documents with uneven lighting or mixed dark/light regions).
#                   Global Otsu (otsu_binarize) also exported for callers that need it.
# • Blur:           applied only when gaussian_noise=True (new behaviour).
# • Morph ops:      both opening (negative_noise) AND closing (unconnected) available.
# • Returns:        global_threshold + was_stretched (new fields kept).
# """

# from PIL import Image
# import math


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 1 — Mode normalisation + loading
# # ═══════════════════════════════════════════════════════════════════════════════

# def _load_normalised(path):
#     """Open any PIL-readable image and return a plain RGB PIL Image."""
#     img  = Image.open(path)
#     mode = img.mode

#     if mode in ("RGBA", "LA"):
#         bg = Image.new("RGB", img.size, (255, 255, 255))
#         if mode == "RGBA":
#             bg.paste(img, mask=img.split()[3])
#         else:
#             bg.paste(img.convert("RGB"))
#         img = bg
#     elif mode == "P":
#         img = img.convert("RGBA").convert("RGB") \
#             if "transparency" in img.info else img.convert("RGB")
#     elif mode == "1":
#         img = img.convert("L").convert("RGB")
#     elif mode == "L":
#         img = img.convert("RGB")
#     elif mode != "RGB":
#         img = img.convert("RGB")

#     return img


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 2 — Grayscale conversion  (BT.601)
# # ═══════════════════════════════════════════════════════════════════════════════

# def _to_grayscale(img):
#     """Y = 0.299R + 0.587G + 0.114B → 2-D list[list[int]] (0-255)."""
#     w, h   = img.size
#     pixels = list(img.getdata())
#     gray   = []
#     for r in range(h):
#         row = []
#         for c in range(w):
#             R, G, B  = pixels[r * w + c]
#             row.append(int(0.299 * R + 0.587 * G + 0.114 * B))
#         gray.append(row)
#     return gray


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 3 — Contrast normalisation  (histogram stretch)
# # ═══════════════════════════════════════════════════════════════════════════════

# def _needs_stretch(gray, low_contrast_threshold=80):
#     h, w = len(gray), len(gray[0])
#     flat = sorted(gray[r][c] for r in range(h) for c in range(w))
#     n    = len(flat)
#     return (flat[int(0.98 * n)] - flat[int(0.02 * n)]) < low_contrast_threshold


# def _stretch_contrast(gray):
#     h, w  = len(gray), len(gray[0])
#     flat  = sorted(gray[r][c] for r in range(h) for c in range(w))
#     n     = len(flat)
#     lo    = flat[int(0.02 * n)]
#     hi    = flat[int(0.98 * n)]
#     if hi == lo:
#         return [row[:] for row in gray]
#     scale = 255.0 / (hi - lo)
#     return [[max(0, min(255, int((gray[r][c] - lo) * scale)))
#              for c in range(w)] for r in range(h)]


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 4 — Gaussian blur  (separable 1-D passes)
# # ═══════════════════════════════════════════════════════════════════════════════

# def _gaussian_kernel_1d(radius):
#     if radius == 0:
#         return [1.0]
#     sigma  = max(radius / 2.0, 0.5)
#     kernel = [math.exp(-((i - radius) ** 2) / (2 * sigma ** 2))
#               for i in range(2 * radius + 1)]
#     total  = sum(kernel)
#     return [k / total for k in kernel]


# def _convolve_h(image, kernel):
#     h, w   = len(image), len(image[0])
#     radius = len(kernel) // 2
#     out    = []
#     for r in range(h):
#         row = []
#         for c in range(w):
#             acc = sum(image[r][min(max(c + ki - radius, 0), w - 1)] * kv
#                       for ki, kv in enumerate(kernel))
#             row.append(acc)
#         out.append(row)
#     return out


# def _convolve_v(image, kernel):
#     h, w   = len(image), len(image[0])
#     radius = len(kernel) // 2
#     out    = [[0.0] * w for _ in range(h)]
#     for r in range(h):
#         for c in range(w):
#             out[r][c] = sum(image[min(max(r + ki - radius, 0), h - 1)][c] * kv
#                             for ki, kv in enumerate(kernel))
#     return out


# def _gaussian_blur(gray, radius):
#     if radius == 0:
#         return gray
#     kernel  = _gaussian_kernel_1d(radius)
#     tmp     = _convolve_h(gray, kernel)
#     blurred = _convolve_v(tmp, kernel)
#     h, w    = len(blurred), len(blurred[0])
#     return [[int(round(blurred[r][c])) for c in range(w)] for r in range(h)]


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 5a — Global Otsu binarization  (exported for standalone use)
# # ═══════════════════════════════════════════════════════════════════════════════

# def otsu_binarize(gray):
#     """
#     Global Otsu binarization.

#     Returns
#     -------
#     binary    : 2-D list[list[int]]  (1=ink, 0=background)
#     threshold : int
#     """
#     flat = [p for row in gray for p in row]
#     hist = [0] * 256
#     for v in flat:
#         hist[v] += 1

#     total     = len(flat)
#     total_sum = sum(i * hist[i] for i in range(256))
#     sum_bg = weight_bg = 0
#     best_var = threshold = 0

#     for t in range(256):
#         weight_bg += hist[t]
#         if weight_bg == 0:
#             continue
#         weight_fg = total - weight_bg
#         if weight_fg == 0:
#             break
#         sum_bg   += t * hist[t]
#         mean_bg   = sum_bg / weight_bg
#         mean_fg   = (total_sum - sum_bg) / weight_fg
#         var       = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
#         if var > best_var:
#             best_var  = var
#             threshold = t

#     threshold -= 5  # small bias toward retaining thin strokes
#     h, w = len(gray), len(gray[0])
#     binary = [[1 if gray[r][c] < threshold else 0 for c in range(w)]
#               for r in range(h)]
#     return binary, threshold


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 5b — Adaptive tiled Otsu binarization  (default — better quality)
# # ═══════════════════════════════════════════════════════════════════════════════

# def _otsu_on_patch(flat_pixels):
#     """Compute Otsu threshold on a flat list of ints (0-255)."""
#     total = len(flat_pixels)
#     if total == 0:
#         return 128
#     hist = [0] * 256
#     for v in flat_pixels:
#         hist[v] += 1
#     best_t = best_var = 0
#     weight_bg = sum_bg = 0
#     total_sum = sum(i * hist[i] for i in range(256))
#     for t in range(256):
#         weight_bg += hist[t]
#         if weight_bg == 0:
#             continue
#         weight_fg = total - weight_bg
#         if weight_fg == 0:
#             break
#         sum_bg += t * hist[t]
#         mean_bg = sum_bg / weight_bg
#         mean_fg = (total_sum - sum_bg) / weight_fg
#         var = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
#         if var > best_var:
#             best_var = var
#             best_t   = t
#     return best_t


# def _adaptive_binarize(gray, tile_size=128):
#     """
#     Adaptive tiled Otsu binarization with bilinear interpolation.

#     Divides the image into tile_size × tile_size tiles, computes an Otsu
#     threshold per tile, then bilinear-interpolates back to full resolution.
#     Much more robust than global Otsu for scanned pages with uneven lighting.

#     Returns
#     -------
#     binary        : 2-D list[list[int]]
#     global_thresh : int   (global Otsu for diagnostics)
#     """
#     h, w = len(gray), len(gray[0])

#     # Global threshold kept for diagnostics / fallback
#     flat_all      = [gray[r][c] for r in range(h) for c in range(w)]
#     global_thresh = _otsu_on_patch(flat_all)

#     # Per-tile thresholds
#     n_rows = max(1, (h + tile_size - 1) // tile_size)
#     n_cols = max(1, (w + tile_size - 1) // tile_size)
#     tile_thresh = []
#     for tr in range(n_rows):
#         row_t = []
#         r0, r1 = tr * tile_size, min((tr + 1) * tile_size, h)
#         for tc in range(n_cols):
#             c0, c1 = tc * tile_size, min((tc + 1) * tile_size, w)
#             patch  = [gray[r][c] for r in range(r0, r1) for c in range(c0, c1)]
#             row_t.append(_otsu_on_patch(patch))
#         tile_thresh.append(row_t)

#     # Bilinear interpolation back to pixel resolution
#     binary = []
#     for r in range(h):
#         row   = []
#         tf    = (r + 0.5) / tile_size - 0.5
#         tr0   = max(0, min(n_rows - 2, int(math.floor(tf))))
#         tr1   = min(tr0 + 1, n_rows - 1)
#         dr    = tf - tr0
#         for c in range(w):
#             cf  = (c + 0.5) / tile_size - 0.5
#             tc0 = max(0, min(n_cols - 2, int(math.floor(cf))))
#             tc1 = min(tc0 + 1, n_cols - 1)
#             dc  = cf - tc0
#             t00 = tile_thresh[tr0][tc0]
#             t01 = tile_thresh[tr0][tc1]
#             t10 = tile_thresh[tr1][tc0]
#             t11 = tile_thresh[tr1][tc1]
#             thr = (t00 * (1-dr) * (1-dc) + t01 * (1-dr) * dc +
#                    t10 * dr     * (1-dc) + t11 * dr     * dc)
#             row.append(1 if gray[r][c] < thr else 0)
#         binary.append(row)

#     return binary, global_thresh


# # ═══════════════════════════════════════════════════════════════════════════════
# # STEP 6 — Morphological operations
# # ═══════════════════════════════════════════════════════════════════════════════

# def _erode(binary):
#     h, w = len(binary), len(binary[0])
#     out  = [[0] * w for _ in range(h)]
#     for r in range(1, h - 1):
#         for c in range(1, w - 1):
#             if (binary[r][c] and
#                     binary[r-1][c-1] and binary[r-1][c] and binary[r-1][c+1] and
#                     binary[r  ][c-1] and                    binary[r  ][c+1] and
#                     binary[r+1][c-1] and binary[r+1][c] and binary[r+1][c+1]):
#                 out[r][c] = 1
#     return out


# def _dilate(binary):
#     h, w = len(binary), len(binary[0])
#     out  = [[0] * w for _ in range(h)]
#     for r in range(1, h - 1):
#         for c in range(1, w - 1):
#             if (binary[r][c] or
#                     binary[r-1][c-1] or binary[r-1][c] or binary[r-1][c+1] or
#                     binary[r  ][c-1] or                   binary[r  ][c+1] or
#                     binary[r+1][c-1] or binary[r+1][c] or binary[r+1][c+1]):
#                 out[r][c] = 1
#     return out


# def _morphological_opening(binary):
#     """Erosion → dilation. Removes isolated speckle pixels."""
#     return _dilate(_erode(binary))


# def _morphological_closing(binary):
#     """Dilation → erosion. Reconnects broken strokes."""
#     return _erode(_dilate(binary))


# # ═══════════════════════════════════════════════════════════════════════════════
# # PUBLIC ENTRY POINT
# # ═══════════════════════════════════════════════════════════════════════════════

# def preprocess(path, gaussian_noise=False, negative_noise=False,
#                unconnected=False, tile_size=128):
#     """
#     Run the full preprocessing pipeline on a single image.

#     Parameters
#     ----------
#     path            : str   path to any PIL-readable image
#     gaussian_noise  : bool  apply Gaussian blur before binarization
#                             (use for scanned images with Gaussian noise)
#     negative_noise  : bool  apply morphological opening after binarization
#                             (use for images with salt/pepper speckle noise)
#     unconnected     : bool  apply morphological closing after binarization
#                             (use for images with broken/disconnected strokes)
#     tile_size       : int   tile side-length for adaptive Otsu (default 128)

#     Returns
#     -------
#     dict:
#         gray             — 2-D list[list[int]]   grayscale values 0-255
#         binary           — 2-D list[list[int]]   0=background, 1=text
#         width            — int
#         height           — int
#         global_threshold — int    global Otsu threshold (diagnostics)
#         was_stretched    — bool   True if contrast stretch was applied
#     """
#     # Step 1: Load
#     img    = _load_normalised(path)
#     gray   = _to_grayscale(img)
#     height = len(gray)
#     width  = len(gray[0])

#     # Step 2: Contrast normalisation
#     was_stretched = False
#     if _needs_stretch(gray):
#         gray          = _stretch_contrast(gray)
#         was_stretched = True

#     # Step 3: Optional Gaussian blur
#     if gaussian_noise:
#         blur_radius = 2 if was_stretched else 1
#         gray        = _gaussian_blur(gray, blur_radius)

#     # Step 4: Adaptive tiled Otsu binarization (better than global for documents)
#     binary, global_threshold = _adaptive_binarize(gray, tile_size=tile_size)

#     # Step 5: Optional morphological cleanup
#     if negative_noise:
#         binary = _morphological_opening(binary)   # remove speckle
#     if unconnected:
#         binary = _morphological_closing(binary)   # reconnect broken strokes

#     return {
#         "gray":             gray,
#         "binary":           binary,
#         "width":            width,
#         "height":           height,
#         "global_threshold": global_threshold,
#         "was_stretched":    was_stretched,
#     }


"""
preprocessing.py  [merged]
================
Stages 1 & 2 of the Equation Detector Pipeline.

Pure Python — Pillow used ONLY for image I/O.

Merge notes
-----------
• API:            new flags-based API kept: gaussian_noise / negative_noise / unconnected
• Binarization:   upgraded to ADAPTIVE TILED OTSU from original v1 (better than global
                  Otsu for documents with uneven lighting or mixed dark/light regions).
                  Global Otsu (otsu_binarize) also exported for callers that need it.
• Blur:           applied only when gaussian_noise=True (new behaviour).
• Morph ops:      both opening (negative_noise) AND closing (unconnected) available.
• Returns:        global_threshold + was_stretched (new fields kept).
"""

from PIL import Image
import math


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Mode normalisation + loading
# ═══════════════════════════════════════════════════════════════════════════════

def _load_normalised(path):
    """Open any PIL-readable image and return a plain RGB PIL Image."""
    img  = Image.open(path)
    mode = img.mode

    if mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if mode == "RGBA":
            bg.paste(img, mask=img.split()[3])
        else:
            bg.paste(img.convert("RGB"))
        img = bg
    elif mode == "P":
        img = img.convert("RGBA").convert("RGB") \
            if "transparency" in img.info else img.convert("RGB")
    elif mode == "1":
        img = img.convert("L").convert("RGB")
    elif mode == "L":
        img = img.convert("RGB")
    elif mode != "RGB":
        img = img.convert("RGB")

    return img


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Grayscale conversion  (BT.601)
# ═══════════════════════════════════════════════════════════════════════════════

def _to_grayscale(img):
    """Y = 0.299R + 0.587G + 0.114B → 2-D list[list[int]] (0-255)."""
    w, h   = img.size
    pixels = list(img.getdata())
    gray   = []
    for r in range(h):
        row = []
        for c in range(w):
            R, G, B  = pixels[r * w + c]
            row.append(int(0.299 * R + 0.587 * G + 0.114 * B))
        gray.append(row)
    return gray


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Contrast normalisation  (histogram stretch)
# ═══════════════════════════════════════════════════════════════════════════════

def _needs_stretch(gray, low_contrast_threshold=120):
    """
    Return True if the image needs contrast stretching.

    Threshold raised from 80 → 120 to catch phone photos and lightly
    faded prints whose dynamic range sits in the 80-120 band. Their
    compressed contrast causes thin equation strokes (fraction bars,
    superscript dots) to sit very close to the binarization boundary,
    which hurts detection accuracy even though the image looks fine visually.
    """
    h, w = len(gray), len(gray[0])
    flat = sorted(gray[r][c] for r in range(h) for c in range(w))
    n    = len(flat)
    return (flat[int(0.98 * n)] - flat[int(0.02 * n)]) < low_contrast_threshold


def _stretch_contrast(gray):
    h, w  = len(gray), len(gray[0])
    flat  = sorted(gray[r][c] for r in range(h) for c in range(w))
    n     = len(flat)
    lo    = flat[int(0.02 * n)]
    hi    = flat[int(0.98 * n)]
    if hi == lo:
        return [row[:] for row in gray]
    scale = 255.0 / (hi - lo)
    return [[max(0, min(255, int((gray[r][c] - lo) * scale)))
             for c in range(w)] for r in range(h)]


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Gaussian blur  (separable 1-D passes)
# ═══════════════════════════════════════════════════════════════════════════════

def _gaussian_kernel_1d(radius):
    if radius == 0:
        return [1.0]
    sigma  = max(radius / 2.0, 0.5)
    kernel = [math.exp(-((i - radius) ** 2) / (2 * sigma ** 2))
              for i in range(2 * radius + 1)]
    total  = sum(kernel)
    return [k / total for k in kernel]


def _convolve_h(image, kernel):
    h, w   = len(image), len(image[0])
    radius = len(kernel) // 2
    out    = []
    for r in range(h):
        row = []
        for c in range(w):
            acc = sum(image[r][min(max(c + ki - radius, 0), w - 1)] * kv
                      for ki, kv in enumerate(kernel))
            row.append(acc)
        out.append(row)
    return out


def _convolve_v(image, kernel):
    h, w   = len(image), len(image[0])
    radius = len(kernel) // 2
    out    = [[0.0] * w for _ in range(h)]
    for r in range(h):
        for c in range(w):
            out[r][c] = sum(image[min(max(r + ki - radius, 0), h - 1)][c] * kv
                            for ki, kv in enumerate(kernel))
    return out


def _gaussian_blur(gray, radius):
    if radius == 0:
        return gray
    kernel  = _gaussian_kernel_1d(radius)
    tmp     = _convolve_h(gray, kernel)
    blurred = _convolve_v(tmp, kernel)
    h, w    = len(blurred), len(blurred[0])
    return [[int(round(blurred[r][c])) for c in range(w)] for r in range(h)]


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5a — Global Otsu binarization  (exported for standalone use)
# ═══════════════════════════════════════════════════════════════════════════════

def otsu_binarize(gray):
    """
    Global Otsu binarization.

    Returns
    -------
    binary    : 2-D list[list[int]]  (1=ink, 0=background)
    threshold : int
    """
    flat = [p for row in gray for p in row]
    hist = [0] * 256
    for v in flat:
        hist[v] += 1

    total     = len(flat)
    total_sum = sum(i * hist[i] for i in range(256))
    sum_bg = weight_bg = 0
    best_var = threshold = 0

    for t in range(256):
        weight_bg += hist[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg   += t * hist[t]
        mean_bg   = sum_bg / weight_bg
        mean_fg   = (total_sum - sum_bg) / weight_fg
        var       = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if var > best_var:
            best_var  = var
            threshold = t

    threshold -= 5  # small bias toward retaining thin strokes
    h, w = len(gray), len(gray[0])
    binary = [[1 if gray[r][c] < threshold else 0 for c in range(w)]
              for r in range(h)]
    return binary, threshold


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5b — Adaptive tiled Otsu binarization  (default — better quality)
# ═══════════════════════════════════════════════════════════════════════════════

def _otsu_on_patch(flat_pixels, clamp_threshold=None):
    """
    Compute Otsu threshold on a flat list of ints (0-255).

    Fix 1 — Thin-tile clamping:
    Tiles that are mostly background (wide margins, whitespace blocks around
    equations) produce inflated thresholds (e.g. 210) that bleed into
    adjacent equation tiles via bilinear interpolation, causing thin strokes
    like fraction bars and superscript dots to be classified as background.

    When clamp_threshold is provided (the global Otsu value), any tile whose
    ink ratio is below 3% is clamped to min(tile_threshold, clamp_threshold).
    This prevents margin tiles from contaminating the interpolated threshold
    map near equation regions.
    """
    total = len(flat_pixels)
    if total == 0:
        return 128
    hist = [0] * 256
    for v in flat_pixels:
        hist[v] += 1
    best_t = best_var = 0
    weight_bg = sum_bg = 0
    total_sum = sum(i * hist[i] for i in range(256))
    for t in range(256):
        weight_bg += hist[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * hist[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (total_sum - sum_bg) / weight_fg
        var = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if var > best_var:
            best_var = var
            best_t   = t

    # Fix 1: clamp whitespace-dominated tiles
    if clamp_threshold is not None:
        # Count dark pixels (potential ink) — below 128
        dark_pixels = sum(hist[v] for v in range(128))
        ink_ratio   = dark_pixels / total
        if ink_ratio < 0.03:          # tile is >97% background
            best_t = min(best_t, clamp_threshold)

    return best_t


def _adaptive_binarize(gray, tile_size=128):
    """
    Adaptive tiled Otsu binarization with bilinear interpolation.

    Divides the image into tile_size x tile_size tiles, computes an Otsu
    threshold per tile, then bilinear-interpolates back to full resolution.
    Much more robust than global Otsu for scanned pages with uneven lighting.

    Fix 1: passes global_thresh to each tile's _otsu_on_patch so whitespace
    tiles are clamped and cannot bleed inflated thresholds into equation areas.

    Fix 2: applies a -5 thin-stroke bias to the final per-pixel threshold,
    matching the global otsu_binarize() path and preserving thin elements
    (fraction bars, superscript dots, integral signs) that sit near the boundary.

    Returns
    -------
    binary        : 2-D list[list[int]]
    global_thresh : int   (global Otsu for diagnostics)
    """
    h, w = len(gray), len(gray[0])

    # Global threshold — used for diagnostics AND as the clamp ceiling
    # for whitespace-dominated tiles (Fix 1)
    flat_all      = [gray[r][c] for r in range(h) for c in range(w)]
    global_thresh = _otsu_on_patch(flat_all)

    # Per-tile thresholds — pass global_thresh for whitespace clamping
    n_rows = max(1, (h + tile_size - 1) // tile_size)
    n_cols = max(1, (w + tile_size - 1) // tile_size)
    tile_thresh = []
    for tr in range(n_rows):
        row_t = []
        r0, r1 = tr * tile_size, min((tr + 1) * tile_size, h)
        for tc in range(n_cols):
            c0, c1 = tc * tile_size, min((tc + 1) * tile_size, w)
            patch  = [gray[r][c] for r in range(r0, r1) for c in range(c0, c1)]
            row_t.append(_otsu_on_patch(patch, clamp_threshold=global_thresh))
        tile_thresh.append(row_t)

    # Bilinear interpolation back to pixel resolution
    # Fix 2: apply +5 thin-stroke bias so the adaptive path preserves the
    # same thin elements that the global path preserves.
    # Logic: global otsu does threshold -= 5, which lowers the bar so more
    # pixels (including thin strokes just above the original threshold) are
    # classified as ink. Equivalent in adaptive: raise the comparison value
    # by 5 (gray < thr + 5), catching those same borderline pixels.
    THIN_STROKE_BIAS = 5
    binary = []
    for r in range(h):
        row   = []
        tf    = (r + 0.5) / tile_size - 0.5
        tr0   = max(0, min(n_rows - 2, int(math.floor(tf))))
        tr1   = min(tr0 + 1, n_rows - 1)
        dr    = tf - tr0
        for c in range(w):
            cf  = (c + 0.5) / tile_size - 0.5
            tc0 = max(0, min(n_cols - 2, int(math.floor(cf))))
            tc1 = min(tc0 + 1, n_cols - 1)
            dc  = cf - tc0
            t00 = tile_thresh[tr0][tc0]
            t01 = tile_thresh[tr0][tc1]
            t10 = tile_thresh[tr1][tc0]
            t11 = tile_thresh[tr1][tc1]
            thr = (t00 * (1-dr) * (1-dc) + t01 * (1-dr) * dc +
                   t10 * dr     * (1-dc) + t11 * dr     * dc)
            row.append(1 if gray[r][c] < thr + THIN_STROKE_BIAS else 0)
        binary.append(row)

    return binary, global_thresh


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6 — Morphological operations
# ═══════════════════════════════════════════════════════════════════════════════

def _erode(binary):
    h, w = len(binary), len(binary[0])
    out  = [[0] * w for _ in range(h)]
    for r in range(1, h - 1):
        for c in range(1, w - 1):
            if (binary[r][c] and
                    binary[r-1][c-1] and binary[r-1][c] and binary[r-1][c+1] and
                    binary[r  ][c-1] and                    binary[r  ][c+1] and
                    binary[r+1][c-1] and binary[r+1][c] and binary[r+1][c+1]):
                out[r][c] = 1
    return out


def _dilate(binary):
    h, w = len(binary), len(binary[0])
    out  = [[0] * w for _ in range(h)]
    for r in range(1, h - 1):
        for c in range(1, w - 1):
            if (binary[r][c] or
                    binary[r-1][c-1] or binary[r-1][c] or binary[r-1][c+1] or
                    binary[r  ][c-1] or                   binary[r  ][c+1] or
                    binary[r+1][c-1] or binary[r+1][c] or binary[r+1][c+1]):
                out[r][c] = 1
    return out


def _morphological_opening(binary):
    """Erosion → dilation. Removes isolated speckle pixels."""
    return _dilate(_erode(binary))


def _morphological_closing(binary):
    """Dilation → erosion. Reconnects broken strokes."""
    return _erode(_dilate(binary))


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def _auto_tile_size(width, height):
    """
    Fix 3 — Auto tile size based on image resolution.

    tile_size=128 is well-suited to 300 DPI documents where 12pt body text
    is ~50px tall (128px = ~2.5 lines). At lower resolutions (phone photos,
    72-150 DPI) body text is 10-25px tall and 128px spans 5-12 lines,
    mixing dense text and equation whitespace in the same tile and producing
    a threshold calibrated for text density — which hurts thin equation strokes.

    Strategy: target ~2-3 text lines per tile. We estimate a rough font size
    from the image height (A4 page assumption: ~50 text lines) and set tile
    size to 3x the estimated line height, clamped to a safe range.

    Result:
      300 DPI A4 (~3508px tall) → font ~47px → tile 96px  (was 128)
      150 DPI A4 (~1754px tall) → font ~23px → tile 48px  (was 128)
       72 DPI A4 ( ~842px tall) → font ~11px → tile 32px  (was 128)
    """
    estimated_font_px = height / 74.0   # A4 at any DPI: ~50 lines × 1.5 spacing
    raw_tile = int(estimated_font_px * 3)
    # Clamp: min 32 (very low-res), max 128 (high-res / standard)
    return max(32, min(128, raw_tile))


def _resize_if_needed(img, max_dim):
    """
    Fix 5 — Downscale large images to prevent slow processing.

    Very high-res scans (600 DPI A4 = 4960×7016) make every preprocessing
    step proportionally slower without improving detection quality, since
    the CCA and scoring stages operate on blobs whose features (height,
    width, area) are all relative to font_size. Clamping to max_dim=2000px
    keeps the longest dimension manageable while preserving all structural
    information needed for equation detection.

    Returns (img, was_resized: bool).
    """
    if max_dim is None:
        return img, False
    w, h = img.size
    if max(w, h) <= max_dim:
        return img, False
    scale = max_dim / max(w, h)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return img.resize((new_w, new_h), Image.LANCZOS), True


def preprocess(path, gaussian_noise=False, negative_noise=False,
               unconnected=False, tile_size=None, max_dim=2000):
    """
    Run the full preprocessing pipeline on a single image.

    Parameters
    ----------
    path            : str        path to any PIL-readable image
    gaussian_noise  : bool       apply Gaussian blur before binarization
                                 (use for scanned images with Gaussian noise)
    negative_noise  : bool       apply morphological opening after binarization
                                 (use for images with salt/pepper speckle noise)
    unconnected     : bool       apply morphological closing after binarization
                                 (use for images with broken/disconnected strokes)
    tile_size       : int|None   tile side-length for adaptive Otsu.
                                 None (default) = auto-select based on image height
                                 (Fix 3: smaller tiles for low-DPI images)
    max_dim         : int|None   clamp the longest image dimension to this value
                                 before processing (Fix 5).  None = no resize.
                                 Default 2000px — safe for all standard DPIs.

    Returns
    -------
    dict:
        gray             — 2-D list[list[int]]   grayscale values 0-255
        binary           — 2-D list[list[int]]   0=background, 1=text
        width            — int
        height           — int
        global_threshold — int    global Otsu threshold (diagnostics)
        was_stretched    — bool   True if contrast stretch was applied
    """
    # Step 1: Load + optional downscale (Fix 5)
    img, _was_resized = _resize_if_needed(_load_normalised(path), max_dim)
    gray   = _to_grayscale(img)
    height = len(gray)
    width  = len(gray[0])

    # Step 2: Contrast normalisation (Fix 4: wider threshold catches phone photos)
    was_stretched = False
    if _needs_stretch(gray):
        gray          = _stretch_contrast(gray)
        was_stretched = True

    # Step 3: Optional Gaussian blur
    if gaussian_noise:
        blur_radius = 2 if was_stretched else 1
        gray        = _gaussian_blur(gray, blur_radius)

    # Step 4: Adaptive tiled Otsu binarization
    # Fix 3: auto tile size if not specified by caller
    effective_tile = tile_size if tile_size is not None else _auto_tile_size(width, height)
    print(f"      tile_size={effective_tile}px  "
          f"({'auto' if tile_size is None else 'caller-set'})")
    # binary, global_threshold = _adaptive_binarize(gray, tile_size=effective_tile)
    binary, global_threshold = _adaptive_binarize(gray, tile_size=effective_tile)


    # Step 5: Optional morphological cleanup
    if negative_noise:
        binary = _morphological_opening(binary)   # remove speckle
    if unconnected:
        binary = _morphological_closing(binary)   # reconnect broken strokes

    return {
        "gray":             gray,
        "binary":           binary,
        "width":            width,
        "height":           height,
        "global_threshold": global_threshold,
        "was_stretched":    was_stretched,
    }