# """
# base.py — DocumentTypeResult dataclass and BaseDocumentTypeDetector interface.

# Every detector (blob, edge, combined) returns a DocumentTypeResult.
# Every detector inherits from BaseDocumentTypeDetector and implements detect().
#   - Blob detector looks at character shapes
#   - Edge detector looks at page-level texture
# """


# # ─────────────────────────────────────────
# # Result dataclass
# # ─────────────────────────────────────────

# class DocumentTypeResult:
#     """
#     Holds the output of any document type detector.

#     Attributes
#     ----------
#     doc_type : str
#         "dense" or "sparse"
#     confidence : float
#         0.0 – 1.0. How confident the detector is in its classification.
#     signals : dict
#         Raw measurements that led to the decision.
#         Keys differ by detector but always present so callers can log them.
#     detector_name : str
#         Which detector produced this result ("blob", "edge", "combined").
#     """

#     def __init__(self, doc_type, confidence, signals, detector_name):
#         if doc_type not in ("dense", "sparse"):
#             raise ValueError(f"doc_type must be 'dense' or 'sparse', got {doc_type!r}")
#         if not 0.0 <= confidence <= 1.0:
#             raise ValueError(f"confidence must be in [0, 1], got {confidence}")

#         self.doc_type      = doc_type
#         self.confidence    = confidence
#         self.signals       = signals
#         self.detector_name = detector_name

#     @property
#     def is_dense(self):
#         return self.doc_type == "dense"

#     @property
#     def is_sparse(self):
#         return self.doc_type == "sparse"

#     def __repr__(self):
#         return (
#             f"DocumentTypeResult("
#             f"doc_type={self.doc_type!r}, "
#             f"confidence={self.confidence:.2f}, "
#             f"detector={self.detector_name!r})"
#         )

#     def summary(self):
#         """Human-readable summary for debug printing."""
#         lines = [
#             f"  Detector : {self.detector_name}",
#             f"  Type     : {self.doc_type.upper()}",
#             f"  Confidence: {self.confidence:.2f}",
#             "  Signals:",
#         ]
#         for k, v in self.signals.items():
#             if isinstance(v, float):
#                 lines.append(f"    {k:<25} {v:.4f}")
#             else:
#                 lines.append(f"    {k:<25} {v}")
#         return "\n".join(lines)


# # ─────────────────────────────────────────
# # Base detector interface
# # ─────────────────────────────────────────

# class BaseDocumentTypeDetector:
#     """
#     Abstract base class for document type detectors.

#     Subclasses must implement detect() and return a DocumentTypeResult.
#     They must also set self.name to a short string identifier.

#     Usage
#     -----
#     detector = BlobDocumentTypeDetector()
#     result   = detector.detect(blobs, font_size, img_width, img_height)
#     print(result.doc_type)   # "dense" or "sparse"
#     """

#     name = "base"  # override in subclass

#     def detect(self, blobs, font_size, img_width, img_height,
#                gray=None, debug=False):
#         """
#         Classify the document as dense or sparse.

#         Parameters
#         ----------
#         blobs       : list of blob dicts (from find_all_blobs)
#         font_size   : int — estimated body text height in pixels
#         img_width   : int
#         img_height  : int
#         gray        : 2D list of int — grayscale pixel values (optional,
#                       needed by edge-based detector)
#         debug       : bool — if True, print internal measurements

#         Returns
#         -------
#         DocumentTypeResult
#         """
#         raise NotImplementedError(
#             f"{self.__class__.__name__} must implement detect()"
#         )

#     def _clamp(self, value, lo=0.0, hi=1.0):
#         """Clamp a value to [lo, hi]."""
#         return max(lo, min(hi, value))


"""
base.py — DocumentTypeResult dataclass and BaseDocumentTypeDetector interface.

Three-class density system
--------------------------
  density_class 0 — SPARSE : exam sheets, assignment pages, slides with few items
  density_class 1 — MEDIUM : lecture notes, mixed slides, annotated papers
  density_class 2 — DENSE  : research papers, textbooks, conference proceedings

Legacy doc_type ("dense"/"sparse") is kept as a derived property so existing
callers do not break:  class 0/1 → "sparse",  class 2 → "dense".
"""

DENSITY_LABELS    = {0: "SPARSE", 1: "MEDIUM", 2: "DENSE"}
_CLASS_TO_DOC_TYPE = {0: "sparse", 1: "sparse", 2: "dense"}


class DocumentTypeResult:
    """
    Attributes
    ----------
    density_class : int   0 / 1 / 2  ← primary output
    doc_type      : str   "sparse" or "dense"  (derived, backward-compat)
    confidence    : float 0–1
    signals       : dict  raw measurements
    detector_name : str
    """

    def __init__(self, density_class, confidence, signals, detector_name):
        if density_class not in (0, 1, 2):
            raise ValueError(f"density_class must be 0, 1, or 2, got {density_class!r}")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {confidence}")

        self.density_class = density_class
        self.confidence    = confidence
        self.signals       = signals
        self.detector_name = detector_name

    # ── Derived legacy properties ─────────────────────────────────────────

    @property
    def doc_type(self):
        return _CLASS_TO_DOC_TYPE[self.density_class]

    @property
    def is_dense(self):
        return self.density_class == 2

    @property
    def is_medium(self):
        return self.density_class == 1

    @property
    def is_sparse(self):
        return self.density_class == 0

    @property
    def density_label(self):
        return DENSITY_LABELS[self.density_class]

    def __repr__(self):
        return (
            f"DocumentTypeResult("
            f"density_class={self.density_class}({self.density_label}), "
            f"conf={self.confidence:.2f}, detector={self.detector_name!r})"
        )

    def summary(self):
        lines = [
            f"  Detector      : {self.detector_name}",
            f"  Density class : {self.density_class}  ({self.density_label})",
            f"  Legacy type   : {self.doc_type}",
            f"  Confidence    : {self.confidence:.2f}",
            "  Signals:",
        ]
        for k, v in self.signals.items():
            if isinstance(v, float):
                lines.append(f"    {k:<28} {v:.4f}")
            else:
                lines.append(f"    {k:<28} {v}")
        return "\n".join(lines)


class BaseDocumentTypeDetector:
    """
    Abstract base.  Subclasses implement detect() → DocumentTypeResult
    with density_class in {0, 1, 2}.
    """

    name = "base"

    def detect(self, blobs, font_size, img_width, img_height,
               gray=None, debug=False):
        raise NotImplementedError(f"{self.__class__.__name__} must implement detect()")

    def _clamp(self, value, lo=0.0, hi=1.0):
        return max(lo, min(hi, value))