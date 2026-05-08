"""Pipeline module for equation detection."""
"""
document_type/ — Document density detection module.

Exports the blob-based detector and result dataclass.
The detector_mode string "blob" (or "combined" for backward compatibility)
maps to BlobDocumentTypeDetector.  The edge and combined detectors have been
removed — the blob detector's connected-component statistics are more reliable
than pixel-level Sobel analysis and measure exactly what matters for equation
detection (character structure, line density).

Usage
-----
    from pipeline.document_type import get_detector

    detector = get_detector("blob")          # or "combined" — same thing
    result   = detector.detect(blobs, font_size, img_width, img_height)

    print(result.density_class)   # 0 = sparse, 1 = medium, 2 = dense
    print(result.doc_type)        # "sparse" or "dense"  (legacy)
    print(result.confidence)
    print(result.signals)
"""

from .base          import DocumentTypeResult, BaseDocumentTypeDetector
from .blob_detector import BlobDocumentTypeDetector

# Kept for import compatibility — both names point to the blob detector
_REGISTRY = {
    "blob":     BlobDocumentTypeDetector,
    "combined": BlobDocumentTypeDetector,   # alias: no longer separate
    "edge":     BlobDocumentTypeDetector,   # alias: edge detector removed
}


def get_detector(mode="blob"):
    """
    Instantiate the document density detector.

    Parameters
    ----------
    mode : str — "blob" (default), "combined", or "edge"
               All three now resolve to BlobDocumentTypeDetector.

    Returns
    -------
    BlobDocumentTypeDetector instance
    """
    if mode not in _REGISTRY:
        raise ValueError(
            f"Unknown detector mode {mode!r}. "
            f"Choose from: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[mode]()


__all__ = [
    "DocumentTypeResult",
    "BaseDocumentTypeDetector",
    "BlobDocumentTypeDetector",
    "get_detector",
]