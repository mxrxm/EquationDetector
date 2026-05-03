"""
edge_detector.py — Document type detection using edge statistics.

Uses Sobel edge analysis (sampled every 4th pixel for speed) to measure:
  1. Overall edge density    — how much edge activity across the page
  2. Horizontal edge ratio   — what fraction of edges are horizontal

"""

import math
from .base import BaseDocumentTypeDetector, DocumentTypeResult


class EdgeDocumentTypeDetector(BaseDocumentTypeDetector):

    name = "edge"

    # Tuned thresholds
    EDGE_DENSITY_DENSE  = 0.06   # fraction of sampled pixels that are edges
    HORIZ_RATIO_DENSE   = 0.52   # fraction of edges that are horizontal

    # Sobel sampling step — every Nth pixel (4 = fast, 1 = precise)
    SAMPLE_STEP = 4

    # ── Internal Sobel runner ─────────────────────────────────────────────

    def _run_sobel(self, gray):
        """
        Sample Sobel over the grayscale image.
        Returns list of (magnitude, abs_gx, abs_gy) tuples.
        Called by both detect() and collect_magnitudes() so the
        computation lives in exactly one place.
        """
        h = len(gray)
        w = len(gray[0])
        s = self.SAMPLE_STEP

        Gx_kernel = [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]
        Gy_kernel = [[ 1, 2, 1], [ 0, 0, 0], [-1,-2,-1]]

        magnitudes = []
        for r in range(1, h - 1, s):
            for c in range(1, w - 1, s):
                gx = gy = 0
                for i in range(-1, 2):
                    for j in range(-1, 2):
                        px  = gray[r + i][c + j]
                        gx += px * Gx_kernel[i + 1][j + 1]
                        gy += px * Gy_kernel[i + 1][j + 1]
                mag = math.sqrt(gx * gx + gy * gy)
                magnitudes.append((mag, abs(gx), abs(gy)))

        return magnitudes

    # ── Public: collect raw magnitudes for visualization ──────────────────

    def collect_magnitudes(self, gray):
        """
        Return the raw list of sampled Sobel magnitudes as plain floats.
        Use this to feed plot_edge_threshold_histogram() without
        rerunning Sobel a second time.

        Parameters
        ----------
        gray : 2D list of int — same image passed to detect()

        Returns
        -------
        magnitudes : list of float
        threshold  : float — the 15%-of-max cutoff used internally
        """
        raw = self._run_sobel(gray)
        if not raw:
            return [], 0.0

        mag_only  = [m[0] for m in raw]
        max_mag   = max(mag_only) or 1.0
        threshold = 0.15 * max_mag

        return mag_only, threshold

    # ── Public: detect document type ──────────────────────────────────────

    def detect(self, blobs, font_size, img_width, img_height,
               gray=None, debug=False):
        """
        Classify document as dense or sparse using edge statistics.

        Parameters
        ----------
        blobs      : unused (accepted for interface compatibility)
        font_size  : unused (accepted for interface compatibility)
        img_width  : int
        img_height : int
        gray       : 2D list of int — required for Sobel computation
        debug      : bool

        Returns
        -------
        DocumentTypeResult
        """
        if gray is None:
            return DocumentTypeResult(
                doc_type="sparse",
                confidence=0.5,
                signals={"reason": "no_gray_image_provided"},
                detector_name=self.name
            )

        # ── Run Sobel via shared helper ───────────────────────────────────
        magnitudes = self._run_sobel(gray)

        if not magnitudes:
            return DocumentTypeResult(
                doc_type="sparse",
                confidence=0.5,
                signals={"reason": "no_pixels_sampled"},
                detector_name=self.name
            )

        total_sampled = len(magnitudes)
        max_mag       = max(m[0] for m in magnitudes) or 1
        threshold     = 0.15 * max_mag

        edge_count  = 0
        horiz_count = 0
        for mag, abs_gx, abs_gy in magnitudes:
            if mag >= threshold:
                edge_count += 1
                if abs_gy > abs_gx:   # horizontal edge = strong vertical gradient
                    horiz_count += 1

        # ── Signal 1: Edge density ────────────────────────────────────────
        edge_density = edge_count / total_sampled

        # ── Signal 2: Horizontal edge ratio ──────────────────────────────
        horiz_ratio  = horiz_count / edge_count if edge_count > 0 else 0.0

        # ── Decision ─────────────────────────────────────────────────────
        votes = 0
        if edge_density >= self.EDGE_DENSITY_DENSE:  votes += 1
        if horiz_ratio  >= self.HORIZ_RATIO_DENSE:   votes += 1

        doc_type       = "dense" if votes == 2 else "sparse"
        confidence_map = {2: 0.85, 1: 0.55, 0: 0.85}
        confidence     = confidence_map[votes]

        signals = {
            "edge_density":         edge_density,
            "edge_density_thresh":  self.EDGE_DENSITY_DENSE,
            "horiz_ratio":          horiz_ratio,
            "horiz_ratio_thresh":   self.HORIZ_RATIO_DENSE,
            "edge_count":           edge_count,
            "total_sampled":        total_sampled,
            "max_magnitude":        max_mag,
            "auto_threshold":       threshold,
            "votes":                votes,
        }

        result = DocumentTypeResult(
            doc_type=doc_type,
            confidence=confidence,
            signals=signals,
            detector_name=self.name
        )

        if debug:
            print(result.summary())

        return result