"""
blob_detector.py — Document density classification using blob statistics.

Three-class output
------------------
  Class 0  SPARSE  — exam sheets, assignment pages, slides with few items
                     Low ink density, low body ratio, few blobs/line.
  Class 1  MEDIUM  — lecture notes, mixed slides, lightly annotated papers
                     Moderate density that fits neither extreme.
  Class 2  DENSE   — research papers, textbooks, conference proceedings
                     High ink density, high body ratio, many blobs/line.

Signals
-------
  1. ink_density      total ink pixels / total image pixels
  2. body_blob_ratio  fraction of blobs whose height ≈ font_size (normal letters)
  3. blobs_per_line   average number of blobs per estimated text line

Each signal votes independently:
  +1  → dense evidence
   0  → medium / ambiguous
  −1  → sparse evidence

Decision
--------
  vote_sum == +3  → class 2 (all three agree: dense)
  vote_sum == −3  → class 0 (all three agree: sparse)
  vote_sum >= +1  → class 1 (leaning dense, not unanimous)
  vote_sum <= −1  → class 0 (leaning sparse — conservative)
  vote_sum ==  0  → class 1 (true middle ground)

Thresholds (tuned at 300 DPI)
------------------------------
                         SPARSE boundary   DENSE boundary
  ink_density            < 0.025           >= 0.055
  body_ratio             < 0.45            >= 0.65
  blobs_per_line         < 12              >= 25
"""

from .base import BaseDocumentTypeDetector, DocumentTypeResult


class BlobDocumentTypeDetector(BaseDocumentTypeDetector):

    name = "blob"

    # Below this → sparse vote
    INK_DENSITY_SPARSE    = 0.025
    BODY_RATIO_SPARSE     = 0.45
    BLOBS_PER_LINE_SPARSE = 12

    # At or above this → dense vote
    INK_DENSITY_DENSE     = 0.055
    BODY_RATIO_DENSE      = 0.65
    BLOBS_PER_LINE_DENSE  = 25

    @staticmethod
    def _vote(value, sparse_thresh, dense_thresh):
        """Return −1 / 0 / +1 for sparse / medium / dense."""
        if value < sparse_thresh:
            return -1
        if value >= dense_thresh:
            return +1
        return 0

    def detect(self, blobs, font_size, img_width, img_height,
               gray=None, debug=False):
        """
        Classify document density from blob statistics.

        Parameters
        ----------
        blobs      : list of blob dicts from blob_analysis.find_all_blobs()
        font_size  : int   estimated body-text height in pixels
        img_width  : int
        img_height : int
        gray       : ignored (accepted for interface compatibility)
        debug      : bool  print signal table if True

        Returns
        -------
        DocumentTypeResult  with density_class in {0, 1, 2}
        """
        if not blobs:
            return DocumentTypeResult(
                density_class=0,
                confidence=1.0,
                signals={"reason": "no_blobs"},
                detector_name=self.name,
            )

        # ── Signal 1: Ink density ──────────────────────────────────────────
        total_pixels = img_width * img_height
        total_ink    = sum(b["area"] for b in blobs)
        ink_density  = total_ink / total_pixels

        # ── Signal 2: Body blob ratio ──────────────────────────────────────
        lo = font_size * 0.60
        hi = font_size * 1.40
        body_blobs = sum(1 for b in blobs if lo <= b["height"] <= hi)
        body_ratio = body_blobs / len(blobs)

        # ── Signal 3: Blobs per estimated line ────────────────────────────
        estimated_lines = max(1, img_height / (font_size * 1.5))
        blobs_per_line  = len(blobs) / estimated_lines

        # ── Per-signal votes ───────────────────────────────────────────────
        v_ink  = self._vote(ink_density,    self.INK_DENSITY_SPARSE,    self.INK_DENSITY_DENSE)
        v_body = self._vote(body_ratio,     self.BODY_RATIO_SPARSE,     self.BODY_RATIO_DENSE)
        v_bpl  = self._vote(blobs_per_line, self.BLOBS_PER_LINE_SPARSE, self.BLOBS_PER_LINE_DENSE)

        vote_sum = v_ink + v_body + v_bpl   # range: −3 … +3

        # ── Decision ──────────────────────────────────────────────────────
        if vote_sum == 3:
            density_class, confidence = 2, 0.90   # unanimous dense
        elif vote_sum == -3:
            density_class, confidence = 0, 0.90   # unanimous sparse
        elif vote_sum >= 1:
            density_class, confidence = 1, 0.65   # leaning dense
        elif vote_sum <= -1:
            density_class, confidence = 0, 0.70   # leaning sparse
        else:
            density_class, confidence = 1, 0.60   # true middle

        signals = {
            "ink_density":            ink_density,
            "ink_density_sparse":     self.INK_DENSITY_SPARSE,
            "ink_density_dense":      self.INK_DENSITY_DENSE,
            "body_ratio":             body_ratio,
            "body_ratio_sparse":      self.BODY_RATIO_SPARSE,
            "body_ratio_dense":       self.BODY_RATIO_DENSE,
            "blobs_per_line":         blobs_per_line,
            "blobs_per_line_sparse":  self.BLOBS_PER_LINE_SPARSE,
            "blobs_per_line_dense":   self.BLOBS_PER_LINE_DENSE,
            "total_blobs":            len(blobs),
            "estimated_lines":        estimated_lines,
            "vote_ink":               v_ink,
            "vote_body":              v_body,
            "vote_bpl":               v_bpl,
            "vote_sum":               vote_sum,
        }

        result = DocumentTypeResult(
            density_class=density_class,
            confidence=confidence,
            signals=signals,
            detector_name=self.name,
        )

        if debug:
            print(result.summary())

        return result