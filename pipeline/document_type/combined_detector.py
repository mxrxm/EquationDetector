"""
combined_detector.py — Runs blob and edge detectors, requires both to agree
for "dense". Either can declare "sparse".

Rationale:
  - The blob detector can be fooled by pages with many small equation symbols
    (lots of tiny blobs → low body ratio → looks sparse even if it's a
    dense paper with one equation block).
  - The edge detector can be fooled by low-contrast scans where edges are weak.
  - Requiring agreement makes false positives on "dense" very unlikely.
  - Disagreement always resolves to "sparse" which is the safer fallback
    (the sparse classifier is more conservative and less likely to miss equations).
"""

from .base import BaseDocumentTypeDetector, DocumentTypeResult
from .blob_detector import BlobDocumentTypeDetector
from .edge_detector import EdgeDocumentTypeDetector


class CombinedDocumentTypeDetector(BaseDocumentTypeDetector):

    name = "combined"

    def __init__(self):
        self._blob = BlobDocumentTypeDetector()
        self._edge = EdgeDocumentTypeDetector()

    def detect(self, blobs, font_size, img_width, img_height,
               gray=None, debug=False):
        """
        Run both detectors and combine their results.

        Rule:
          - BOTH say dense  → dense  (high confidence)
          - EITHER says sparse → sparse (safe fallback)

        Parameters
        ----------
        blobs      : list of blob dicts
        font_size  : int
        img_width  : int
        img_height : int
        gray       : 2D list of int — passed through to edge detector
        debug      : bool

        Returns
        -------
        DocumentTypeResult with both sub-results stored in signals
        """

        if debug:
            print("\n── Blob detector ──")
        blob_result = self._blob.detect(
            blobs, font_size, img_width, img_height,
            gray=gray, debug=debug
        )

        if debug:
            print("\n── Edge detector ──")
        edge_result = self._edge.detect(
            blobs, font_size, img_width, img_height,
            gray=gray, debug=debug
        )

        # ── Combination rule ──────────────────────────────────────────────
        both_dense   = blob_result.is_dense and edge_result.is_dense
        either_sparse = blob_result.is_sparse or edge_result.is_sparse

        if both_dense:
            doc_type   = "dense"
            # Confidence = geometric mean of both detector confidences
            confidence = (blob_result.confidence * edge_result.confidence) ** 0.5
            agreement  = "both_dense"
        else:
            doc_type   = "sparse"
            # If they disagree, lower confidence
            if blob_result.doc_type != edge_result.doc_type:
                confidence = 0.60
                agreement  = "disagreement_fallback_sparse"
            else:
                # Both said sparse
                confidence = (blob_result.confidence * edge_result.confidence) ** 0.5
                agreement  = "both_sparse"

        signals = {
            "agreement":           agreement,
            "blob_type":           blob_result.doc_type,
            "blob_confidence":     blob_result.confidence,
            "edge_type":           edge_result.doc_type,
            "edge_confidence":     edge_result.confidence,
            # Expose key sub-signals for logging
            "ink_density":         blob_result.signals.get("ink_density", 0),
            "body_ratio":          blob_result.signals.get("body_ratio", 0),
            "blobs_per_line":      blob_result.signals.get("blobs_per_line", 0),
            "edge_density":        edge_result.signals.get("edge_density", 0),
            "horiz_ratio":         edge_result.signals.get("horiz_ratio", 0),
        }

        result = DocumentTypeResult(
            doc_type=doc_type,
            confidence=confidence,
            signals=signals,
            detector_name=self.name
        )

        if debug:
            print("\n── Combined result ──")
            print(result.summary())

        return result