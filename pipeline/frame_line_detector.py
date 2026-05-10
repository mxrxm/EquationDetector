"""
Line / frame detector — pipeline/line_frame_detector.py

Removes blobs that are large horizontal/vertical line segments or page-border
frame components before region grouping.

Place in pipeline AFTER blob_analysis (so font_size is already estimated) and
BEFORE region_grouping.  Call:

    clean_blobs, rejected = filter_line_blobs(blobs, image_w, image_h, font_size)

then pass `clean_blobs` to group_blobs_into_regions.
"""

from __future__ import annotations
from typing import TypedDict


# ── types ────────────────────────────────────────────────────────────────────

class Blob(TypedDict):
    x1: int; y1: int; x2: int; y2: int


class FilterResult(TypedDict):
    clean_blobs:       list      # list[Blob]
    rejected_blobs:    list      # list[Blob]
    rejection_reasons: dict      # dict[int, str]


# ── tuneable defaults ────────────────────────────────────────────────────────

# A blob is a "thin line" if its short axis < font_size * this factor
THIN_AXIS_FONT_FACTOR: float = 0.6

# A blob is "long" enough to be a line if its long axis spans this fraction
# of the corresponding image dimension
LINE_SPAN_FACTOR: float = 0.15          # 40 % of image width/height

# Frame detection: a blob that hugs a page edge within this many pixels of the
# image border is treated as a frame stroke even if it is thicker than a line
BORDER_MARGIN_PX: int = 12

# Aspect-ratio threshold: long / short axis must exceed this to be "line-like"
ASPECT_RATIO_MIN: float = 6.0


# ── helpers ──────────────────────────────────────────────────────────────────

def _blob_dims(blob: Blob) -> tuple[int, int, int, int]:
    """Return w, h, short_axis, long_axis."""
    w = blob["x2"] - blob["x1"]
    h = blob["y2"] - blob["y1"]
    short = min(w, h)
    long  = max(w, h)
    return w, h, short, long


def _is_horizontal_line(blob: Blob, image_w: int, thin_px: float,
                         span_px: float) -> bool:
    w, h, short, long = _blob_dims(blob)
    if w < h:           # taller than wide → not horizontal
        return False
    return (h <= thin_px
            and w >= span_px
            and (w / max(h, 1)) >= ASPECT_RATIO_MIN)


def _is_vertical_line(blob: Blob, image_h: int, thin_px: float,
                       span_px_v: float) -> bool:
    w, h, short, long = _blob_dims(blob)
    if h < w:           # wider than tall → not vertical
        return False
    return (w <= thin_px
            and h >= span_px_v
            and (h / max(w, 1)) >= ASPECT_RATIO_MIN)


def _is_frame_stroke(blob: Blob, image_w: int, image_h: int) -> bool:
    """
    True if the blob runs along any of the four page edges (border margin).
    Catches thick frames that are too wide to be "thin lines" but clearly hug
    the page boundary.
    """
    x1, y1, x2, y2 = blob["x1"], blob["y1"], blob["x2"], blob["y2"]
    m = BORDER_MARGIN_PX

    touches_left   = x1 <= m
    touches_right  = x2 >= image_w - m
    touches_top    = y1 <= m
    touches_bottom = y2 >= image_h - m

    w, h, _, _ = _blob_dims(blob)

    # A horizontal frame stroke: touches top or bottom AND is wide
    if (touches_top or touches_bottom) and w >= image_w * LINE_SPAN_FACTOR:
        return True
    # A vertical frame stroke: touches left or right AND is tall
    if (touches_left or touches_right) and h >= image_h * LINE_SPAN_FACTOR:
        return True

    return False


# ── public API ───────────────────────────────────────────────────────────────

def filter_line_blobs(
    blobs:    list[Blob],
    image_w:  int,
    image_h:  int,
    font_size: float,
    *,
    thin_axis_factor: float = THIN_AXIS_FONT_FACTOR,
    line_span_factor: float = LINE_SPAN_FACTOR,
    border_margin_px: int   = BORDER_MARGIN_PX,
) -> FilterResult:
    """
    Partition *blobs* into content blobs and line/frame blobs.

    Parameters
    ----------
    blobs           : raw blob list from blob_analysis
    image_w/image_h : pixel dimensions of the source image
    font_size       : estimated font size (pixels) from blob_analysis
    thin_axis_factor: short-axis threshold = font_size × this
    line_span_factor: minimum fraction of image dimension to qualify as a line
    border_margin_px: pixel tolerance for "hugging the page edge"

    Returns
    -------
    FilterResult with clean_blobs, rejected_blobs, rejection_reasons
    """
    thin_px    = font_size * thin_axis_factor
    span_px_h  = image_w  * line_span_factor   # horizontal span threshold
    span_px_v  = image_h  * line_span_factor   # vertical   span threshold

    # Override module-level constants with call-site values so helpers see them
    global BORDER_MARGIN_PX
    _saved_margin = BORDER_MARGIN_PX
    BORDER_MARGIN_PX = border_margin_px

    clean:    list[Blob] = []
    rejected: list[Blob] = []
    reasons:  dict[int, str] = {}

    for idx, blob in enumerate(blobs):
        reason: str | None = None

        if _is_horizontal_line(blob, image_w, thin_px, span_px_h):
            reason = "horizontal_line"
        elif _is_vertical_line(blob, image_h, thin_px, span_px_v):
            reason = "vertical_line"
        elif _is_frame_stroke(blob, image_w, image_h):
            reason = "frame_stroke"

        if reason:
            rejected.append(blob)
            reasons[idx] = reason
        else:
            clean.append(blob)

    BORDER_MARGIN_PX = _saved_margin   # restore

    print(f"  Line filter: {len(rejected)} blob(s) removed "
          f"({len(clean)} remaining)  "
          f"[h_line={sum(1 for r in reasons.values() if r=='horizontal_line')}, "
          f" v_line={sum(1 for r in reasons.values() if r=='vertical_line')}, "
          f" frame={sum(1 for r in reasons.values() if r=='frame_stroke')}]")

    return {
        "clean_blobs":       clean,
        "rejected_blobs":    rejected,
        "rejection_reasons": reasons,
    }