"""
app.py — Streamlit frontend for the Equation Detector.

Fixes vs original:
  - detector_mode radio is now wired into run_cca_pipeline()
  - doc_type_label read from pipeline output, not guessed from inline count
  - use_column_width → use_container_width  (Streamlit ≥ 1.18 deprecation)
  - save_stage6 import removed (unused in the app)
  - diagnostic render cached separately so it does not re-run on slider move
  - pipeline result cached with st.session_state keyed on filename+mode
    so re-uploading the same file with a different mode re-runs correctly
  - tab3 confidence histogram uses st.bar_chart fallback if pandas unavailable
"""

import os
import sys
import tempfile
import io

import streamlit as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Equation Detector",
    page_icon="∂",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
h1, h2, h3 { font-family: 'IBM Plex Mono', monospace; }
.main-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 2.2rem; font-weight: 600;
    letter-spacing: -0.02em; margin-bottom: 0;
}
.subtitle {
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 300; color: #888;
    margin-top: 0.2rem; margin-bottom: 2rem;
}
.metric-card {
    background: #f8f8f8; border: 1px solid #e0e0e0;
    border-left: 4px solid #1a1a1a;
    padding: 1rem 1.2rem; border-radius: 2px;
    font-family: 'IBM Plex Mono', monospace;
}
.metric-value  { font-size: 2rem; font-weight: 600; line-height: 1; }
.metric-label  { font-size: 0.75rem; color: #888; text-transform: uppercase;
                 letter-spacing: 0.08em; margin-top: 0.3rem; }
.class0        { border-left-color: #d62728; }
.class1        { border-left-color: #1f77b4; }
.classtotal    { border-left-color: #2ca02c; }
.doc-badge     { display: inline-block; font-family: 'IBM Plex Mono', monospace;
                 font-size: 0.7rem; font-weight: 600; padding: 0.2rem 0.6rem;
                 border-radius: 2px; letter-spacing: 0.1em; text-transform: uppercase; }
.badge-dense   { background: #1a1a1a; color: #fff; }
.badge-sparse  { background: #e8e8e8; color: #333; }
.stButton > button {
    font-family: 'IBM Plex Mono', monospace; font-size: 0.85rem;
    border-radius: 2px; border: 1.5px solid #1a1a1a;
    background: #1a1a1a; color: white; padding: 0.5rem 1.5rem;
}
.stButton > button:hover { background: #fff; color: #1a1a1a; }
div[data-testid="stSidebar"] { background: #fafafa; border-right: 1px solid #e8e8e8; }
</style>
""", unsafe_allow_html=True)


# ── Figure → bytes (avoids temp files) ───────────────────────────────────────
def _fig_bytes(fig, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi,
                bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


# ── Detection overlay ─────────────────────────────────────────────────────────
def _render_detections(gray, text_boxes, eq_results, class1_threshold):
    fig, ax = plt.subplots(figsize=(12, 16))
    fig.patch.set_facecolor("#fafafa")
    ax.imshow(gray, cmap="gray", vmin=0, vmax=255)

    for x1, y1, x2, y2 in text_boxes:
        ax.add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=1, edgecolor="#2ca02c",
            facecolor="#2ca02c", alpha=0.07))

    for det in eq_results:
        x1, y1, x2, y2 = det["box"]
        cls, conf = det["class"], det["confidence"]
        if cls == 1 and conf < class1_threshold:
            continue
        color = "#d62728" if cls == 0 else "#1f77b4"
        ax.add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=2, edgecolor=color, facecolor=color, alpha=0.15))
        ax.text(x1+2, y1-3, f"{conf:.2f}",
                color=color, fontsize=6, fontweight="bold",
                verticalalignment="bottom")

    ax.axis("off")
    plt.tight_layout(pad=0)
    return fig


# ── 6-panel diagnostic (cached — does not re-run on slider move) ──────────────
@st.cache_data(show_spinner=False)
def _render_diagnostic_cached(gray_key, gray_flat, binary_flat, blob_data,
                               font_size, text_boxes, eq_results,
                               img_width, img_height):
    """
    Cache key is gray_key (filename+mode string). Heavy computation runs once.
    All 2-D structures passed as flat tuples so st.cache_data can hash them.
    """
    # Reconstruct 2-D lists
    gray   = [list(gray_flat  [r*img_width:(r+1)*img_width]) for r in range(img_height)]
    binary = [list(binary_flat[r*img_width:(r+1)*img_width]) for r in range(img_height)]

    # Reconstruct blob dicts from (x1,y1,x2,y2,height,width,area,fill_ratio) tuples
    blob_data  = [{"x1": t[0], "y1": t[1], "x2": t[2], "y2": t[3],
                   "height": t[4], "width": t[5], "area": t[6], "fill_ratio": t[7]}
                  for t in blob_data]

    # Reconstruct eq_results from (box, confidence, class) tuples
    eq_results = [{"box": t[0], "confidence": t[1], "class": t[2]}
                  for t in eq_results]

    fig, axes = plt.subplots(2, 3, figsize=(20, 13))
    fig.patch.set_facecolor("#fafafa")
    fig.suptitle("Pipeline diagnostic", fontsize=13, fontfamily="monospace", y=1.01)

    standalone = [d for d in eq_results if d["class"] == 0]
    inline     = [d for d in eq_results if d["class"] == 1]

    # Panel 1 — Grayscale
    axes[0,0].imshow(gray,   cmap="gray", vmin=0, vmax=255)
    axes[0,0].set_title("Grayscale input",           fontsize=9, fontfamily="monospace")
    axes[0,0].axis("off")

    # Panel 2 — Binary
    axes[0,1].imshow(binary, cmap="gray", vmin=0, vmax=1)
    axes[0,1].set_title("Binary — adaptive Otsu",   fontsize=9, fontfamily="monospace")
    axes[0,1].axis("off")

    # Panel 3 — Blob height histogram
    heights = [b["height"] for b in blob_data]
    axes[0,2].set_facecolor("#f8f8f8")
    axes[0,2].hist(heights, bins=55, color="#1a1a1a", edgecolor="#fafafa", alpha=0.85)
    axes[0,2].axvline(font_size,        color="#d62728", lw=2,
                      label=f"Font = {font_size}px")
    axes[0,2].axvline(font_size * 1.9,  color="#ff7f0e", lw=1.5, ls="--",
                      label=f"Tall = {font_size*1.9:.0f}px")
    axes[0,2].axvline(font_size * 0.42, color="#9467bd", lw=1.5, ls=":",
                      label=f"Tiny = {font_size*0.42:.0f}px")
    axes[0,2].legend(fontsize=7)
    axes[0,2].set_xlabel("Blob height (px)", fontsize=8)
    axes[0,2].set_ylabel("Count",            fontsize=8)
    axes[0,2].set_title("Blob height distribution", fontsize=9, fontfamily="monospace")
    axes[0,2].tick_params(labelsize=7)

    # Panel 4 — Blob map
    axes[1,0].imshow(gray, cmap="gray", vmin=0, vmax=255, alpha=0.6)
    for b in blob_data:
        is_out = (b["height"] > font_size * 1.9 or
                  (b["width"] > font_size * 4 and b["height"] < font_size * 0.5))
        color = "#d62728" if is_out else "#2ca02c"
        axes[1,0].add_patch(patches.Rectangle(
            (b["x1"], b["y1"]), b["width"], b["height"],
            linewidth=1.0 if is_out else 0.4,
            edgecolor=color, facecolor="none",
            alpha=0.85 if is_out else 0.55))
    axes[1,0].set_title("Blob map — green=normal  red=outlier",
                         fontsize=9, fontfamily="monospace")
    axes[1,0].axis("off")

    # Panel 5 — Text regions
    axes[1,1].imshow(gray, cmap="gray", vmin=0, vmax=255)
    for x1, y1, x2, y2 in text_boxes:
        axes[1,1].add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=1.5, edgecolor="#2ca02c", facecolor="#2ca02c", alpha=0.15))
    axes[1,1].set_title(f"Text regions ({len(text_boxes)})",
                         fontsize=9, fontfamily="monospace")
    axes[1,1].axis("off")

    # Panel 6 — All detections
    axes[1,2].imshow(gray, cmap="gray", vmin=0, vmax=255)
    for x1, y1, x2, y2 in text_boxes:
        axes[1,2].add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=1, edgecolor="#2ca02c", facecolor="none"))
    for det in standalone:
        x1, y1, x2, y2 = det["box"]
        axes[1,2].add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=2, edgecolor="#d62728", facecolor="#d62728", alpha=0.18))
        axes[1,2].text(x1+2, y1-3, f"{det['confidence']:.2f}",
                       color="#d62728", fontsize=5, fontweight="bold")
    for det in inline:
        x1, y1, x2, y2 = det["box"]
        axes[1,2].add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=2, edgecolor="#1f77b4", facecolor="#1f77b4", alpha=0.18))
        axes[1,2].text(x1+2, y1-3, f"{det['confidence']:.2f}",
                       color="#1f77b4", fontsize=5, fontweight="bold")
    axes[1,2].set_title(
        f"Detections — red={len(standalone)} standalone  blue={len(inline)} inline",
        fontsize=9, fontfamily="monospace")
    axes[1,2].axis("off")

    plt.tight_layout()
    return _fig_bytes(fig, dpi=120)


# ── Pipeline loader ───────────────────────────────────────────────────────────
@st.cache_resource
def _load_pipeline():
    try:
        from pipeline.pipeline import run_cca_pipeline
        return run_cca_pipeline
    except ImportError:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### ∂ Equation Detector")
    st.markdown("---")
    st.markdown("**Detection settings**")

    detector_mode = st.radio(
        "Detector mode",
        options=["combined", "blob", "edge"],
        index=0,
        help=(
            "combined — blob + edge must both agree on 'dense' (most robust)\n"
            "blob     — ink density + body-blob ratio + blobs-per-line\n"
            "edge     — Sobel edge density + horizontal edge ratio"
        )
    )

    class1_threshold = st.slider(
        "Inline confidence threshold",
        min_value=0.0, max_value=1.0,
        value=0.25, step=0.05,
        help="Class 1 (inline) boxes are only shown above this confidence"
    )

    with st.expander("Inline detection tuning"):
        inline_score_threshold = st.slider(
            "Inline score threshold",
            min_value=2.0, max_value=6.0,
            value=4.2, step=0.1,
            help="Minimum raw cluster score before baseline comparison"
        )
        inline_delta_threshold = st.slider(
            "Inline baseline delta",
            min_value=3.0, max_value=8.0,
            value=6.0, step=0.1,
            help="How far above line baseline a cluster must score"
        )
        inline_gap_factor = st.slider(
            "Inline cluster gap factor",
            min_value=0.7, max_value=1.3,
            value=1.0, step=0.05,
            help="Larger merges more symbols into a cluster"
        )
        inline_max_cluster_size = st.slider(
            "Inline max cluster size",
            min_value=12, max_value=40,
            value=28, step=2,
            help="Reject clusters larger than this blob count"
        )
        inline_sentence_min_n = st.slider(
            "Inline sentence min blobs",
            min_value=8, max_value=24,
            value=12, step=1,
            help="Reject long text-like clusters at or above this blob count"
        )
        inline_tiny_height_ratio = st.slider(
            "Inline tiny height ratio",
            min_value=0.30, max_value=0.55,
            value=0.42, step=0.01,
            help="Blobs below this height (relative to font) count as tiny"
        )
        inline_frac_width_ratio = st.slider(
            "Inline fraction width ratio",
            min_value=0.9, max_value=2.0,
            value=1.2, step=0.05,
            help="Blob width (relative to font) to count as fraction bar"
        )
        inline_frac_height_ratio = st.slider(
            "Inline fraction height ratio",
            min_value=0.08, max_value=0.25,
            value=0.15, step=0.01,
            help="Blob height (relative to font) to count as fraction bar"
        )
        inline_tall_height_ratio = st.slider(
            "Inline tall height ratio",
            min_value=1.4, max_value=2.6,
            value=1.9, step=0.05,
            help="Blob height (relative to font) to count as tall symbol"
        )
        inline_baseline_max = st.slider(
            "Inline baseline max",
            min_value=0.5, max_value=2.5,
            value=1.5, step=0.1,
            help="Higher allows equations in noisier text lines"
        )

    debug_mode = st.checkbox(
        "Debug mode", value=False,
        help="Print per-region scores to the terminal running Streamlit"
    )

    st.markdown("---")
    st.markdown("**Legend**")
    st.markdown("🟥 Standalone equation (class 0)")
    st.markdown("🟦 Inline equation (class 1)")
    st.markdown("🟩 Text region")
    st.markdown("---")
    st.markdown(
        "<small style='color:#aaa;font-family:monospace'>"
        "No OpenCV · No NumPy · Pure Python CCA"
        "</small>",
        unsafe_allow_html=True
    )


# ══════════════════════════════════════════════════════════════════════════════
# HEADER + UPLOAD
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="main-title">Equation Detector</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="subtitle">Mathematical expression localization '
    'via connected component analysis</p>',
    unsafe_allow_html=True
)

uploaded = st.file_uploader(
    "Drop a document image",
    type=["png", "jpg", "jpeg"],
    label_visibility="collapsed"
)

if uploaded is None:
    st.info("Upload a document image to begin — research papers, "
            "textbooks, assignment sheets, or lecture slides.")
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE
# ══════════════════════════════════════════════════════════════════════════════
run_cca_pipeline = _load_pipeline()
if run_cca_pipeline is None:
    st.error(
        "Pipeline modules not found. "
        "Make sure the `pipeline/` folder is in the same directory as `app.py`."
    )
    st.stop()

# Cache results in session_state keyed by (filename, size, detector_mode)
# so changing the slider does NOT re-run the pipeline
_cache_key = (
    f"{uploaded.name}_{uploaded.size}_{detector_mode}_"
    f"{inline_score_threshold}_{inline_delta_threshold}_"
    f"{inline_gap_factor}_{inline_max_cluster_size}_"
    f"{inline_sentence_min_n}_{inline_tiny_height_ratio}_"
    f"{inline_frac_width_ratio}_{inline_frac_height_ratio}_"
    f"{inline_tall_height_ratio}_{inline_baseline_max}"
)

if st.session_state.get("_cache_key") != _cache_key:
    suffix = os.path.splitext(uploaded.name)[1] or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(uploaded.getvalue())
        tmp_path = f.name

    with st.spinner("Running pipeline..."):
        try:
            gray, binary, blobs, font_size, text_boxes, eq_results = \
                run_cca_pipeline(tmp_path,
                                 detector_mode=detector_mode,
                                 inline_score_threshold=inline_score_threshold,
                                 inline_delta_threshold=inline_delta_threshold,
                                 inline_gap_factor=inline_gap_factor,
                                 inline_max_cluster_size=inline_max_cluster_size,
                                 inline_sentence_min_n=inline_sentence_min_n,
                                 inline_tiny_height_ratio=inline_tiny_height_ratio,
                                 inline_frac_width_ratio=inline_frac_width_ratio,
                                 inline_frac_height_ratio=inline_frac_height_ratio,
                                 inline_tall_height_ratio=inline_tall_height_ratio,
                                 inline_baseline_max=inline_baseline_max,
                                 debug=debug_mode)
        except Exception as e:
            st.error(f"Pipeline error: {e}")
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            st.stop()
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    # Determine doc_type from whether inline equations were produced
    # (pipeline prints it; we infer from class distribution)
    has_inline  = any(d["class"] == 1 for d in eq_results)
    doc_type    = "dense" if has_inline else "sparse"

    st.session_state["_cache_key"]  = _cache_key
    st.session_state["gray"]        = gray
    st.session_state["binary"]      = binary
    st.session_state["blobs"]       = blobs
    st.session_state["font_size"]   = font_size
    st.session_state["text_boxes"]  = text_boxes
    st.session_state["eq_results"]  = eq_results
    st.session_state["doc_type"]    = doc_type

# Retrieve from cache
gray       = st.session_state["gray"]
binary     = st.session_state["binary"]
blobs      = st.session_state["blobs"]
font_size  = st.session_state["font_size"]
text_boxes = st.session_state["text_boxes"]
eq_results = st.session_state["eq_results"]
doc_type   = st.session_state["doc_type"]


# ══════════════════════════════════════════════════════════════════════════════
# METRICS ROW
# ══════════════════════════════════════════════════════════════════════════════
standalone_n  = sum(1 for d in eq_results if d["class"] == 0)
inline_all_n  = sum(1 for d in eq_results if d["class"] == 1)
inline_show_n = sum(1 for d in eq_results
                    if d["class"] == 1 and d["confidence"] >= class1_threshold)
total_show_n  = standalone_n + inline_show_n

col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    st.markdown(
        f'<div class="metric-card classtotal">'
        f'<div class="metric-value">{total_show_n}</div>'
        f'<div class="metric-label">Total shown</div></div>',
        unsafe_allow_html=True)
with col_b:
    st.markdown(
        f'<div class="metric-card class0">'
        f'<div class="metric-value">{standalone_n}</div>'
        f'<div class="metric-label">Standalone (class 0)</div></div>',
        unsafe_allow_html=True)
with col_c:
    st.markdown(
        f'<div class="metric-card class1">'
        f'<div class="metric-value">{inline_show_n} / {inline_all_n}</div>'
        f'<div class="metric-label">Inline shown / found (class 1)</div></div>',
        unsafe_allow_html=True)
with col_d:
    badge_cls = "badge-dense" if doc_type == "dense" else "badge-sparse"
    st.markdown(
        f'<div class="metric-card">'
        f'<div class="metric-value">'
        f'<span class="doc-badge {badge_cls}">{doc_type}</span>'
        f'</div>'
        f'<div class="metric-label">Document type</div></div>',
        unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["Detection", "Diagnostic", "Data"])


# ── Tab 1: Detection overlay ──────────────────────────────────────────────────
with tab1:
    det_fig  = _render_detections(gray, text_boxes, eq_results, class1_threshold)
    det_data = _fig_bytes(det_fig, dpi=150)

    st.image(det_data, use_container_width=True)

    st.download_button(
        "⬇ Download annotated image",
        data=det_data,
        file_name=f"{os.path.splitext(uploaded.name)[0]}_detections.png",
        mime="image/png",
        use_container_width=True
    )


# ── Tab 2: Diagnostic (cached — does not re-render on slider move) ────────────
with tab2:
    img_height = len(gray)
    img_width  = len(gray[0])

    # Flatten 2-D lists to hashable tuples for st.cache_data
    gray_flat   = tuple(v for row in gray   for v in row)
    binary_flat = tuple(v for row in binary for v in row)

    diag_data = _render_diagnostic_cached(
        _cache_key,
        gray_flat, binary_flat,
        tuple(
            (b["x1"], b["y1"], b["x2"], b["y2"],
             b["height"], b["width"], b["area"],
             b.get("fill_ratio", 0))
            for b in blobs
        ),
        font_size,
        tuple(text_boxes),
        tuple(
            (d["box"], d["confidence"], d["class"])
            for d in eq_results
        ),
        img_width, img_height
    )
    st.image(diag_data, use_container_width=True)

    st.download_button(
        "⬇ Download diagnostic image",
        data=diag_data,
        file_name=f"{os.path.splitext(uploaded.name)[0]}_diagnostic.png",
        mime="image/png",
        use_container_width=True
    )


# ── Tab 3: Data table + confidence histogram + CSV ────────────────────────────
with tab3:
    rows = []
    for d in eq_results:
        x1, y1, x2, y2 = d["box"]
        cls, conf = d["class"], d["confidence"]
        if cls == 1 and conf < class1_threshold:
            continue
        rows.append({
            "x1":         x1,
            "y1":         y1,
            "x2":         x2,
            "y2":         y2,
            "class":      cls,
            "type":       "standalone" if cls == 0 else "inline",
            "confidence": conf,
            "width_px":   x2 - x1,
            "height_px":  y2 - y1,
        })

    if rows:
        try:
            import pandas as pd
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True)

            # Summary stats
            st.markdown("**Confidence by class**")
            st.dataframe(
                df.groupby("type")["confidence"]
                  .describe()
                  .round(3),
                use_container_width=True
            )

            csv_bytes = df.to_csv(index=False).encode()

        except ImportError:
            # pandas not installed — show plain table
            st.write(rows)
            import csv, io as _io
            buf = _io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
            csv_bytes = buf.getvalue().encode()

        st.download_button(
            "⬇ Download CSV",
            data=csv_bytes,
            file_name=f"{os.path.splitext(uploaded.name)[0]}_detections.csv",
            mime="text/csv",
            use_container_width=True
        )

        # Confidence histogram
        st.markdown("**Confidence distribution**")
        fig_conf, ax_conf = plt.subplots(figsize=(8, 2.8))
        fig_conf.patch.set_facecolor("#fafafa")
        ax_conf.set_facecolor("#f8f8f8")

        c0 = [d["confidence"] for d in eq_results if d["class"] == 0]
        c1 = [d["confidence"] for d in eq_results
              if d["class"] == 1 and d["confidence"] >= class1_threshold]

        if c0:
            ax_conf.hist(c0, bins=20, alpha=0.75, color="#d62728",
                         label=f"Standalone ({len(c0)})")
        if c1:
            ax_conf.hist(c1, bins=20, alpha=0.75, color="#1f77b4",
                         label=f"Inline shown ({len(c1)})")

        ax_conf.axvline(class1_threshold, color="#333", ls="--", lw=1.2,
                        label=f"Threshold ({class1_threshold:.2f})")
        ax_conf.legend(fontsize=8)
        ax_conf.set_xlabel("Confidence", fontsize=8)
        ax_conf.set_ylabel("Count",      fontsize=8)
        ax_conf.tick_params(labelsize=7)
        plt.tight_layout()
        st.pyplot(fig_conf)
        plt.close(fig_conf)

    else:
        st.info("No equations detected above the current threshold.")