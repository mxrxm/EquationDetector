"""
edge_detector.py — Document type detection using edge statistics.

Uses Sobel edge analysis (sampled every 4th pixel for speed) to measure:
  1. Overall edge density    — how much edge activity across the page
  2. Horizontal edge ratio   — what fraction of edges are horizontal

Why horizontal edges?
  Dense text (body paragraphs) produces strong horizontal baselines —
  the tops and bottoms of letter rows create consistent horizontal edges.
  Sparse documents (exam sheets with equations and whitespace) have a lower
  horizontal edge ratio because equations break baseline regularity.

This detector is complementary to the blob detector:
  - Blob detector looks at character shapes
  - Edge detector looks at page-level texture
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
            # Cannot run without grayscale image — fall back to sparse
            return DocumentTypeResult(
                doc_type="sparse",
                confidence=0.5,
                signals={"reason": "no_gray_image_provided"},
                detector_name=self.name
            )

        # ── Sobel edge detection (sampled) ────────────────────────────────
        h = len(gray)
        w = len(gray[0])
        s = self.SAMPLE_STEP

        Gx_kernel = [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]
        Gy_kernel = [[ 1, 2, 1], [ 0, 0, 0], [-1,-2,-1]]

        edge_count   = 0
        horiz_count  = 0
        total_sampled = 0

        # Otsu-style automatic threshold on sampled magnitudes
        # We collect magnitudes first, then threshold
        magnitudes = []

        for r in range(1, h - 1, s):
            for c in range(1, w - 1, s):
                gx = 0
                gy = 0
                for i in range(-1, 2):
                    for j in range(-1, 2):
                        px  = gray[r + i][c + j]
                        gx += px * Gx_kernel[i + 1][j + 1]
                        gy += px * Gy_kernel[i + 1][j + 1]

                mag = math.sqrt(gx * gx + gy * gy)
                magnitudes.append((mag, abs(gx), abs(gy)))
                total_sampled += 1

        if total_sampled == 0:
            return DocumentTypeResult(
                doc_type="sparse",
                confidence=0.5,
                signals={"reason": "no_pixels_sampled"},
                detector_name=self.name
            )

        # Automatic threshold: 15% of max magnitude
        max_mag   = max(m[0] for m in magnitudes) or 1
        threshold = 0.15 * max_mag

        for mag, abs_gx, abs_gy in magnitudes:
            if mag >= threshold:
                edge_count  += 1
                # Horizontal edge = strong Gy (vertical gradient = horizontal line)
                if abs_gy > abs_gx:
                    horiz_count += 1

        # ── Signal 1: Edge density ─────────────────────────────────────────
        edge_density  = edge_count / total_sampled

        # ── Signal 2: Horizontal edge ratio ───────────────────────────────
        horiz_ratio   = horiz_count / edge_count if edge_count > 0 else 0.0

        # ── Decision ──────────────────────────────────────────────────────
        votes = 0
        if edge_density >= self.EDGE_DENSITY_DENSE:  votes += 1
        if horiz_ratio  >= self.HORIZ_RATIO_DENSE:   votes += 1

        # Both signals must agree for "dense"
        doc_type   = "dense" if votes == 2 else "sparse"

        confidence_map = {2: 0.85, 1: 0.55, 0: 0.85}
        confidence = confidence_map[votes]

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