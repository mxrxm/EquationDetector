"""
base.py — DocumentTypeResult dataclass and BaseDocumentTypeDetector interface.

Every detector (blob, edge, combined) returns a DocumentTypeResult.
Every detector inherits from BaseDocumentTypeDetector and implements detect().
  - Blob detector looks at character shapes
  - Edge detector looks at page-level texture
"""


# ─────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────

class DocumentTypeResult:
    """
    Holds the output of any document type detector.

    Attributes
    ----------
    doc_type : str
        "dense" or "sparse"
    confidence : float
        0.0 – 1.0. How confident the detector is in its classification.
    signals : dict
        Raw measurements that led to the decision.
        Keys differ by detector but always present so callers can log them.
    detector_name : str
        Which detector produced this result ("blob", "edge", "combined").
    """

    def __init__(self, doc_type, confidence, signals, detector_name):
        if doc_type not in ("dense", "sparse"):
            raise ValueError(f"doc_type must be 'dense' or 'sparse', got {doc_type!r}")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {confidence}")

        self.doc_type      = doc_type
        self.confidence    = confidence
        self.signals       = signals
        self.detector_name = detector_name

    @property
    def is_dense(self):
        return self.doc_type == "dense"

    @property
    def is_sparse(self):
        return self.doc_type == "sparse"

    def __repr__(self):
        return (
            f"DocumentTypeResult("
            f"doc_type={self.doc_type!r}, "
            f"confidence={self.confidence:.2f}, "
            f"detector={self.detector_name!r})"
        )

    def summary(self):
        """Human-readable summary for debug printing."""
        lines = [
            f"  Detector : {self.detector_name}",
            f"  Type     : {self.doc_type.upper()}",
            f"  Confidence: {self.confidence:.2f}",
            "  Signals:",
        ]
        for k, v in self.signals.items():
            if isinstance(v, float):
                lines.append(f"    {k:<25} {v:.4f}")
            else:
                lines.append(f"    {k:<25} {v}")
        return "\n".join(lines)


# ─────────────────────────────────────────
# Base detector interface
# ─────────────────────────────────────────

class BaseDocumentTypeDetector:
    """
    Abstract base class for document type detectors.

    Subclasses must implement detect() and return a DocumentTypeResult.
    They must also set self.name to a short string identifier.

    Usage
    -----
    detector = BlobDocumentTypeDetector()
    result   = detector.detect(blobs, font_size, img_width, img_height)
    print(result.doc_type)   # "dense" or "sparse"
    """

    name = "base"  # override in subclass

    def detect(self, blobs, font_size, img_width, img_height,
               gray=None, debug=False):
        """
        Classify the document as dense or sparse.

        Parameters
        ----------
        blobs       : list of blob dicts (from find_all_blobs)
        font_size   : int — estimated body text height in pixels
        img_width   : int
        img_height  : int
        gray        : 2D list of int — grayscale pixel values (optional,
                      needed by edge-based detector)
        debug       : bool — if True, print internal measurements

        Returns
        -------
        DocumentTypeResult
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement detect()"
        )

    def _clamp(self, value, lo=0.0, hi=1.0):
        """Clamp a value to [lo, hi]."""
        return max(lo, min(hi, value))