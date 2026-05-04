"""
blob_detector.py — Document type detection using blob statistics.

Uses three signals derived from the CCA blob list:
  1. Ink density       — total ink pixels / total image pixels
  2. Body blob ratio   — fraction of blobs within normal letter height range
  3. Blobs per line    — average number of blobs per estimated text line

Dense documents (research papers, textbooks) have:
  - High ink density  (lots of text, small margins)
  - High body ratio   (mostly uniform letter-height blobs)
  - Many blobs/line   (columns of text packed tightly)

Sparse documents (assignment sheets, exam papers) have:
  - Lower ink density (whitespace between questions)
  - Lower body ratio  (equations introduce outlier-height blobs)
  - Fewer blobs/line  (shorter lines, more whitespace)
"""

import math
from .base import BaseDocumentTypeDetector, DocumentTypeResult


class BlobDocumentTypeDetector(BaseDocumentTypeDetector):

    name = "blob"

    # Thresholds — tuned on 300 DPI documents
    # Ink density: research paper ≈ 0.06–0.12, exam sheet ≈ 0.02–0.05
    INK_DENSITY_DENSE    = 0.04

    # Body blob ratio: dense text ≈ 0.70–0.85, mixed ≈ 0.50–0.65
    BODY_RATIO_DENSE     = 0.65

    # Blobs per estimated line: dense ≈ 30–60, sparse ≈ 10–25
    BLOBS_PER_LINE_DENSE = 25

    def detect(self, blobs, font_size, img_width, img_height,
               gray=None, debug=False):
        """
        Classify document as dense or sparse using blob statistics.

        Parameters
        ----------
        blobs      : list of blob dicts
        font_size  : int — estimated body text height in px
        img_width  : int
        img_height : int
        gray       : unused (accepted for interface compatibility)
        debug      : bool

        Returns
        -------
        DocumentTypeResult
        """

        if not blobs:
            return DocumentTypeResult(
                doc_type="sparse",
                confidence=1.0,
                signals={"reason": "no_blobs"},
                detector_name=self.name
            )

        # ── Signal 1: Ink density ──────────────────────────────────────────
        total_pixels = img_width * img_height
        total_ink    = sum(b["area"] for b in blobs)
        ink_density  = total_ink / total_pixels

        # ── Signal 2: Body blob ratio ──────────────────────────────────────
        # "Body" blobs are blobs whose height is within 40% of font size —
        # i.e., normal lowercase and uppercase letters
        lo = font_size * 0.60
        hi = font_size * 1.40
        body_blobs = sum(1 for b in blobs if lo <= b["height"] <= hi)
        body_ratio = body_blobs / len(blobs)

        # ── Signal 3: Blobs per estimated line ────────────────────────────
        # Estimate number of lines: image height / (font_size × line spacing)
        line_spacing     = font_size * 1.5
        estimated_lines  = max(1, img_height / line_spacing)
        blobs_per_line   = len(blobs) / estimated_lines

        # ── Decision ──────────────────────────────────────────────────────
        # Each signal votes +1 for dense, 0 for sparse
        votes = 0
        if ink_density   >= self.INK_DENSITY_DENSE:    votes += 1
        if body_ratio    >= self.BODY_RATIO_DENSE:     votes += 1
        if blobs_per_line >= self.BLOBS_PER_LINE_DENSE: votes += 1

        # Require all 3 signals to agree for "dense"
        # This avoids false positives on pages with a few dense equations
        doc_type   = "dense" if votes == 3 else "sparse"

        # Confidence: how strongly do the signals agree?
        # 3/3 = fully confident, 2/3 = moderate, 1/3 or 0/3 = confident sparse
        confidence_map = {3: 0.90, 2: 0.60, 1: 0.75, 0: 0.90}
        confidence = confidence_map[votes]

        signals = {
            "ink_density":          ink_density,
            "ink_density_thresh":   self.INK_DENSITY_DENSE,
            "body_ratio":           body_ratio,
            "body_ratio_thresh":    self.BODY_RATIO_DENSE,
            "blobs_per_line":       blobs_per_line,
            "blobs_per_line_thresh": self.BLOBS_PER_LINE_DENSE,
            "total_blobs":          len(blobs),
            "estimated_lines":      estimated_lines,
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