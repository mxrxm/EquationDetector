"""
visualize.py — Modular visualization functions for the equation detector.

Every function returns a matplotlib Figure so it works both standalone
and in Streamlit via st.pyplot(fig).

Usage in Streamlit
------------------
from visualize import (
    plot_binary, plot_blob_height_histogram,
    plot_edge_threshold_histogram, plot_blob_map,
    plot_text_only, plot_equations_only,
    plot_inline_only, plot_all_detections,
    plot_pipeline_grid
)

st.pyplot(plot_binary(gray, binary))
st.pyplot(plot_blob_height_histogram(blobs, font_size))

# For edge histogram — get magnitudes from the detector, not recomputed:
from pipeline.document_type import EdgeDocumentTypeDetector
detector   = EdgeDocumentTypeDetector()
mags, thr  = detector.collect_magnitudes(gray)
st.pyplot(plot_edge_threshold_histogram(mags, thr))
"""

import matplotlib
matplotlib.use("Agg")   # non-interactive backend — safe for Streamlit
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.ticker as ticker


# ─────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────

def _show_image(ax, gray):
    ax.imshow(gray, cmap="gray", vmin=0, vmax=255)
    ax.axis("off")


def _add_box(ax, x1, y1, x2, y2, color, alpha=0.18, lw=2, label=None):
    rect = patches.Rectangle(
        (x1, y1), x2 - x1, y2 - y1,
        linewidth=lw, edgecolor=color,
        facecolor=color, alpha=alpha
    )
    ax.add_patch(rect)
    if label:
        ax.text(x1 + 2, y1 - 4, label,
                color=color, fontsize=6,
                fontweight="bold", verticalalignment="bottom")


def _annotate(ax, text, loc="upper right"):
    xmap = {"upper right": 0.98, "upper left": 0.02}
    ha   = "right" if "right" in loc else "left"
    ax.annotate(
        text,
        xy=(xmap.get(loc, 0.98), 0.97),
        xycoords="axes fraction",
        ha=ha, va="top", fontsize=9,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.75)
    )


# ─────────────────────────────────────────
# 1 — Binary image
# ─────────────────────────────────────────

def plot_binary(gray, binary, figsize=(14, 8)):
    """
    Side-by-side grayscale input and Otsu binary result.

    Parameters
    ----------
    gray   : 2D list[int]
    binary : 2D list[int]  (ink=1, background=0)

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, axes = plt.subplots(1, 2, figsize=figsize)
    fig.suptitle("Stage 2 — Binarization (Otsu)", fontsize=13, y=1.01)

    axes[0].imshow(gray, cmap="gray", vmin=0, vmax=255)
    axes[0].set_title("Grayscale input")
    axes[0].axis("off")

    axes[1].imshow(binary, cmap="gray", vmin=0, vmax=1)
    axes[1].set_title("Binary — ink = white, background = black")
    axes[1].axis("off")

    plt.tight_layout()
    return fig


# ─────────────────────────────────────────
# 2 — Blob height histogram
# ─────────────────────────────────────────

def plot_blob_height_histogram(blobs, font_size, figsize=(9, 5)):
    """
    Histogram of blob heights with font-size, tall-symbol,
    and tiny-symbol marker lines.

    Parameters
    ----------
    blobs     : list of blob dicts (from find_all_blobs)
    font_size : int — estimated body text height in px

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)

    if not blobs:
        ax.set_title("No blobs found")
        return fig

    heights = [b["height"] for b in blobs]

    ax.hist(heights, bins=60, color="#4C9BE8",
            edgecolor="white", linewidth=0.4, label="Blob heights")

    # Font size — modal letter height
    ax.axvline(font_size, color="#EF4444", linewidth=2.0,
               label=f"Font size = {font_size}px")

    # Tall threshold — symbols taller than this are likely equation symbols
    tall = font_size * 1.9
    ax.axvline(tall, color="#F59E0B", linewidth=1.5, linestyle="--",
               label=f"Tall threshold = {tall:.0f}px")

    # Tiny threshold — subscripts / superscripts
    tiny = font_size * 0.42
    ax.axvline(tiny, color="#8B5CF6", linewidth=1.5, linestyle=":",
               label=f"Tiny threshold = {tiny:.0f}px")

    ax.set_title("Stage 3 — Blob height distribution", fontsize=12)
    ax.set_xlabel("Blob height (px)")
    ax.set_ylabel("Count")
    ax.legend(fontsize=9)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    tall_count = sum(1 for h in heights if h > tall)
    tiny_count = sum(1 for h in heights if h < tiny)
    _annotate(ax,
              f"Total blobs : {len(blobs)}\n"
              f"Tall outliers: {tall_count}\n"
              f"Tiny outliers: {tiny_count}")

    plt.tight_layout()
    return fig


# ─────────────────────────────────────────
# 3 — Edge magnitude histogram
#     Uses pre-collected magnitudes from EdgeDocumentTypeDetector
#     — no Sobel recomputation here
# ─────────────────────────────────────────

def plot_edge_threshold_histogram(magnitudes, threshold, figsize=(9, 5)):
    """
    Histogram of Sobel edge magnitudes collected by
    EdgeDocumentTypeDetector.collect_magnitudes().

    Parameters
    ----------
    magnitudes : list of float — raw Sobel magnitudes (sampled)
    threshold  : float         — the 15%-of-max cutoff used by the detector

    Returns
    -------
    matplotlib.figure.Figure

    Example
    -------
    from pipeline.document_type import EdgeDocumentTypeDetector
    detector  = EdgeDocumentTypeDetector()
    mags, thr = detector.collect_magnitudes(gray)
    fig = plot_edge_threshold_histogram(mags, thr)
    """
    fig, ax = plt.subplots(figsize=figsize)

    if not magnitudes:
        ax.set_title("No edge data — gray image not available")
        return fig

    max_mag = max(magnitudes)

    ax.hist(magnitudes, bins=80, color="#34D399",
            edgecolor="white", linewidth=0.3, label="Edge magnitudes")

    ax.axvline(threshold, color="#EF4444", linewidth=2.0,
               label=f"Threshold = {threshold:.1f}  (15% of max)")

    # Shade below-threshold (ignored) region
    ax.axvspan(0, threshold, alpha=0.08, color="gray")
    ax.axvspan(threshold, max_mag * 1.02, alpha=0.06, color="#34D399")

    above = sum(1 for m in magnitudes if m >= threshold)
    below = len(magnitudes) - above

    ax.set_title("Edge magnitude distribution (Sobel, sampled)", fontsize=12)
    ax.set_xlabel("Sobel magnitude")
    ax.set_ylabel("Count (sampled pixels)")
    ax.legend(fontsize=9)

    _annotate(ax,
              f"Sampled px  : {len(magnitudes):,}\n"
              f"Above thresh: {above:,} ({100*above/len(magnitudes):.1f}%)\n"
              f"Max mag     : {max_mag:.1f}")

    plt.tight_layout()
    return fig


# ─────────────────────────────────────────
# 4 — Blob map (normal vs outlier)
# ─────────────────────────────────────────

def plot_blob_map(gray, blobs, font_size, figsize=(10, 13)):
    """
    Overlay all blob bounding boxes on the grayscale image.
    Green = normal letter-height blobs.
    Red   = outlier blobs (tall or wide+flat → likely equation symbols).

    Parameters
    ----------
    gray      : 2D list[int]
    blobs     : list of blob dicts
    font_size : int

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)
    _show_image(ax, gray)

    tall_thresh = font_size * 1.9
    wide_thresh = font_size * 4.0
    flat_thresh = font_size * 0.5

    normal_n = outlier_n = 0

    for b in blobs:
        is_outlier = (
            b["height"] > tall_thresh or
            (b["width"] > wide_thresh and b["height"] < flat_thresh)
        )
        color = "#EF4444" if is_outlier else "#22C55E"
        lw    = 1.0       if is_outlier else 0.5
        alpha = 0.9       if is_outlier else 0.6

        ax.add_patch(patches.Rectangle(
            (b["x1"], b["y1"]), b["width"], b["height"],
            linewidth=lw, edgecolor=color,
            facecolor="none", alpha=alpha
        ))

        if is_outlier:
            outlier_n += 1
        else:
            normal_n  += 1

    ax.set_title(
        f"Stage 4 — Blob map\n"
        f"green = normal ({normal_n})   red = outlier ({outlier_n})",
        fontsize=11
    )
    plt.tight_layout()
    return fig


# ─────────────────────────────────────────
# 5 — Text regions only
# ─────────────────────────────────────────

def plot_text_only(gray, text_boxes, figsize=(10, 13)):
    """
    Show only the regions classified as plain text (green boxes).

    Parameters
    ----------
    gray       : 2D list[int]
    text_boxes : list of (x1, y1, x2, y2) tuples

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)
    _show_image(ax, gray)

    for (x1, y1, x2, y2) in text_boxes:
        _add_box(ax, x1, y1, x2, y2,
                 color="#22C55E", alpha=0.15, lw=1.5)

    ax.set_title(f"Stage 5 — Text regions ({len(text_boxes)})", fontsize=12)
    _annotate(ax, f"Text regions: {len(text_boxes)}", loc="upper left")
    plt.tight_layout()
    return fig


# ─────────────────────────────────────────
# 6 — Standalone equations only (class 0)
# ─────────────────────────────────────────

def plot_equations_only(gray, eq_results, figsize=(10, 13)):
    """
    Show only standalone equation detections (class 0, red boxes).

    Parameters
    ----------
    gray       : 2D list[int]
    eq_results : list of dicts {box, confidence, class}

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)
    _show_image(ax, gray)

    standalone = [d for d in eq_results if d["class"] == 0]

    for det in standalone:
        x1, y1, x2, y2 = det["box"]
        _add_box(ax, x1, y1, x2, y2,
                 color="#EF4444", alpha=0.18, lw=2,
                 label=f"{det['confidence']:.2f}")

    ax.set_title(
        f"Standalone equations (class 0) — {len(standalone)} detected",
        fontsize=12
    )
    _annotate(ax, f"Standalone eq: {len(standalone)}", loc="upper left")
    plt.tight_layout()
    return fig


# ─────────────────────────────────────────
# 7 — Inline equations only (class 1)
# ─────────────────────────────────────────

def plot_inline_only(gray, eq_results, figsize=(10, 13)):
    """
    Show only inline equation detections (class 1, blue boxes).

    Parameters
    ----------
    gray       : 2D list[int]
    eq_results : list of dicts {box, confidence, class}

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)
    _show_image(ax, gray)

    inline = [d for d in eq_results if d["class"] == 1]

    for det in inline:
        x1, y1, x2, y2 = det["box"]
        _add_box(ax, x1, y1, x2, y2,
                 color="#3B82F6", alpha=0.18, lw=2,
                 label=f"{det['confidence']:.2f}")

    ax.set_title(
        f"Inline equations (class 1) — {len(inline)} detected",
        fontsize=12
    )
    _annotate(ax, f"Inline eq: {len(inline)}", loc="upper left")
    plt.tight_layout()
    return fig


# ─────────────────────────────────────────
# 8 — All detections overlay
# ─────────────────────────────────────────

def plot_all_detections(gray, text_boxes, eq_results, figsize=(10, 13)):
    """
    Full detection overlay — text, standalone equations, inline equations.

    green = text regions
    red   = standalone equations (class 0)
    blue  = inline equations (class 1)

    Parameters
    ----------
    gray       : 2D list[int]
    text_boxes : list of (x1, y1, x2, y2)
    eq_results : list of dicts {box, confidence, class}

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)
    _show_image(ax, gray)

    # Draw text first so equation boxes sit on top
    for (x1, y1, x2, y2) in text_boxes:
        _add_box(ax, x1, y1, x2, y2,
                 color="#22C55E", alpha=0.12, lw=1)

    standalone = [d for d in eq_results if d["class"] == 0]
    inline     = [d for d in eq_results if d["class"] == 1]

    for det in standalone:
        x1, y1, x2, y2 = det["box"]
        _add_box(ax, x1, y1, x2, y2,
                 color="#EF4444", alpha=0.20, lw=2,
                 label=f"{det['confidence']:.2f}")

    for det in inline:
        x1, y1, x2, y2 = det["box"]
        _add_box(ax, x1, y1, x2, y2,
                 color="#3B82F6", alpha=0.20, lw=2,
                 label=f"{det['confidence']:.2f}")

    ax.set_title(
        f"All detections — "
        f"green=text ({len(text_boxes)})  "
        f"red=standalone ({len(standalone)})  "
        f"blue=inline ({len(inline)})",
        fontsize=11
    )
    plt.tight_layout()
    return fig


# ─────────────────────────────────────────
# 9 — Full 6-panel diagnostic grid
# ─────────────────────────────────────────

def plot_pipeline_grid(gray, binary, blobs, font_size,
                       text_boxes, eq_results,
                       magnitudes=None, threshold=None,
                       figsize=(22, 14)):
    """
    6-panel diagnostic overview of the full pipeline.

    Panel layout:
      [grayscale]  [binary]         [blob histogram]
      [blob map]   [text only]      [all detections]

    If magnitudes and threshold are provided, the blob histogram panel
    is replaced with the edge magnitude histogram.

    Parameters
    ----------
    gray        : 2D list[int]
    binary      : 2D list[int]
    blobs       : list of blob dicts
    font_size   : int
    text_boxes  : list of (x1,y1,x2,y2)
    eq_results  : list of dicts {box, confidence, class}
    magnitudes  : list of float or None
                  — from EdgeDocumentTypeDetector.collect_magnitudes()
    threshold   : float or None

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, axes = plt.subplots(2, 3, figsize=figsize)
    fig.suptitle("CCA Equation Detector — Full Pipeline", fontsize=15, y=1.01)

    standalone = [d for d in eq_results if d["class"] == 0]
    inline     = [d for d in eq_results if d["class"] == 1]

    # ── Panel 1: Grayscale ──────────────────────────────────────────────
    axes[0, 0].imshow(gray, cmap="gray", vmin=0, vmax=255)
    axes[0, 0].set_title("Stage 1 — Grayscale input")
    axes[0, 0].axis("off")

    # ── Panel 2: Binary ─────────────────────────────────────────────────
    axes[0, 1].imshow(binary, cmap="gray", vmin=0, vmax=1)
    axes[0, 1].set_title("Stage 2 — Binary (Otsu, inverted)")
    axes[0, 1].axis("off")

    # ── Panel 3: Histogram (edge if available, else blob heights) ────────
    if magnitudes and threshold is not None:
        max_mag = max(magnitudes)
        axes[0, 2].hist(magnitudes, bins=80, color="#34D399",
                        edgecolor="white", linewidth=0.3)
        axes[0, 2].axvline(threshold, color="#EF4444", linewidth=2,
                           label=f"Threshold={threshold:.1f}")
        axes[0, 2].set_title("Stage 3 — Edge magnitude distribution")
        axes[0, 2].set_xlabel("Sobel magnitude")
        axes[0, 2].set_ylabel("Count")
        axes[0, 2].legend(fontsize=8)
    else:
        heights = [b["height"] for b in blobs]
        axes[0, 2].hist(heights, bins=60, color="#4C9BE8",
                        edgecolor="white", linewidth=0.4)
        axes[0, 2].axvline(font_size, color="#EF4444", linewidth=2,
                           label=f"Font={font_size}px")
        axes[0, 2].axvline(font_size * 1.9, color="#F59E0B",
                           linewidth=1.5, linestyle="--",
                           label=f"Tall={font_size*1.9:.0f}px")
        axes[0, 2].axvline(font_size * 0.42, color="#8B5CF6",
                           linewidth=1.5, linestyle=":",
                           label=f"Tiny={font_size*0.42:.0f}px")
        axes[0, 2].set_title("Stage 3 — Blob height distribution")
        axes[0, 2].set_xlabel("Blob height (px)")
        axes[0, 2].set_ylabel("Count")
        axes[0, 2].legend(fontsize=8)

    # ── Panel 4: Blob map ───────────────────────────────────────────────
    axes[1, 0].imshow(gray, cmap="gray", vmin=0, vmax=255, alpha=0.6)
    tall_thresh = font_size * 1.9
    wide_thresh = font_size * 4.0
    flat_thresh = font_size * 0.5
    for b in blobs:
        is_out = (b["height"] > tall_thresh or
                  (b["width"] > wide_thresh and b["height"] < flat_thresh))
        color = "#EF4444" if is_out else "#22C55E"
        axes[1, 0].add_patch(patches.Rectangle(
            (b["x1"], b["y1"]), b["width"], b["height"],
            linewidth=0.5 if not is_out else 1.0,
            edgecolor=color, facecolor="none",
            alpha=0.6 if not is_out else 0.9
        ))
    axes[1, 0].set_title("Stage 4 — Blob map (green=normal, red=outlier)")
    axes[1, 0].axis("off")

    # ── Panel 5: Text only ──────────────────────────────────────────────
    axes[1, 1].imshow(gray, cmap="gray", vmin=0, vmax=255)
    for (x1, y1, x2, y2) in text_boxes:
        axes[1, 1].add_patch(patches.Rectangle(
            (x1, y1), x2 - x1, y2 - y1,
            linewidth=1.5, edgecolor="#22C55E",
            facecolor="#22C55E", alpha=0.15
        ))
    axes[1, 1].set_title(f"Stage 5 — Text regions ({len(text_boxes)})")
    axes[1, 1].axis("off")

    # ── Panel 6: All detections ─────────────────────────────────────────
    axes[1, 2].imshow(gray, cmap="gray", vmin=0, vmax=255)
    for (x1, y1, x2, y2) in text_boxes:
        axes[1, 2].add_patch(patches.Rectangle(
            (x1, y1), x2 - x1, y2 - y1,
            linewidth=1, edgecolor="#22C55E", facecolor="none"
        ))
    for det in standalone:
        x1, y1, x2, y2 = det["box"]
        axes[1, 2].add_patch(patches.Rectangle(
            (x1, y1), x2 - x1, y2 - y1,
            linewidth=2, edgecolor="#EF4444",
            facecolor="#EF4444", alpha=0.18
        ))
        axes[1, 2].text(x1 + 2, y1 - 3, f"{det['confidence']:.2f}",
                        color="#EF4444", fontsize=5, fontweight="bold")
    for det in inline:
        x1, y1, x2, y2 = det["box"]
        axes[1, 2].add_patch(patches.Rectangle(
            (x1, y1), x2 - x1, y2 - y1,
            linewidth=2, edgecolor="#3B82F6",
            facecolor="#3B82F6", alpha=0.18
        ))
        axes[1, 2].text(x1 + 2, y1 - 3, f"{det['confidence']:.2f}",
                        color="#3B82F6", fontsize=5, fontweight="bold")
    axes[1, 2].set_title(
        f"Stage 6 — red=standalone ({len(standalone)})  "
        f"blue=inline ({len(inline)})",
        fontsize=10
    )
    axes[1, 2].axis("off")

    plt.tight_layout()
    return fig