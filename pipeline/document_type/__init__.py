"""
document_type/ — Pluggable document type detection module.

Exports three detector classes and the result dataclass.
The detector_mode string maps to the correct class so pipeline.py
can instantiate by name without importing all three.

Usage
-----
from pipeline.document_type import get_detector

detector = get_detector("combined")
result   = detector.detect(blobs, font_size, img_width, img_height, gray=gray)

print(result.doc_type)      # "dense" or "sparse"
print(result.confidence)    # 0.0 – 1.0
print(result.signals)       # dict of raw measurements
"""

from .base             import DocumentTypeResult, BaseDocumentTypeDetector
from .blob_detector    import BlobDocumentTypeDetector
from .edge_detector    import EdgeDocumentTypeDetector
from .combined_detector import CombinedDocumentTypeDetector

# Registry — maps mode string to detector class
_REGISTRY = {
    "blob":     BlobDocumentTypeDetector,
    "edge":     EdgeDocumentTypeDetector,
    "combined": CombinedDocumentTypeDetector,
}


def get_detector(mode="combined"):
    """
    Instantiate a document type detector by mode name.

    Parameters
    ----------
    mode : str — "blob", "edge", or "combined" (default)

    Returns
    -------
    BaseDocumentTypeDetector subclass instance

    Raises
    ------
    ValueError if mode is not recognized
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
    "EdgeDocumentTypeDetector",
    "CombinedDocumentTypeDetector",
    "get_detector",
]