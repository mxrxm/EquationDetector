import streamlit as st
import os
import tempfile
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image
import io

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Equation Detector",
    page_icon="∂",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}

h1, h2, h3 {
    font-family: 'IBM Plex Mono', monospace;
}

.main-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 2.4rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    margin-bottom: 0;
}

.subtitle {
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 300;
    color: #888;
    margin-top: 0.2rem;
    margin-bottom: 2rem;
}

.metric-card {
    background: #f8f8f8;
    border: 1px solid #e0e0e0;
    border-left: 4px solid #1a1a1a;
    padding: 1rem 1.2rem;
    border-radius: 2px;
    font-family: 'IBM Plex Mono', monospace;
}

.metric-value {
    font-size: 2rem;
    font-weight: 600;
    line-height: 1;
}

.metric-label {
    font-size: 0.75rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 0.3rem;
}

.class0 { border-left-color: #d62728; }
.class1 { border-left-color: #1f77b4; }
.classtotal { border-left-color: #2ca02c; }

.doc-badge {
    display: inline-block;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.2rem 0.6rem;
    border-radius: 2px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}

.badge-dense {
    background: #1a1a1a;
    color: #fff;
}

.badge-sparse {
    background: #e8e8e8;
    color: #333;
}

.stButton > button {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
    border-radius: 2px;
    border: 1.5px solid #1a1a1a;
    background: #1a1a1a;
    color: white;
    padding: 0.5rem 1.5rem;
}

.stButton > button:hover {
    background: #fff;
    color: #1a1a1a;
}

div[data-testid="stSidebar"] {
    background: #fafafa;
    border-right: 1px solid #e8e8e8;
}
</style>
""", unsafe_allow_html=True)


# ── Lazy pipeline import ──────────────────────────────────────────────────────
@st.cache_resource
def load_pipeline():
    try:
        from pipeline.pipeline import run_cca_pipeline
        from output.export import save_stage6
        return run_cca_pipeline, save_stage6
    except ImportError:
        return None, None


# ── Inline plotting (no file needed) ─────────────────────────────────────────
def render_detections(gray, text_boxes, eq_results, class1_threshold=0.0):
    fig, ax = plt.subplots(figsize=(12, 16))
    ax.imshow(gray, cmap="gray", vmin=0, vmax=255)

    for det in eq_results:
        x1, y1, x2, y2 = det["box"]
        cls   = det["class"]
        conf  = det["confidence"]
        if cls == 1 and conf < class1_threshold:
            continue
        color = "#d62728" if cls == 0 else "#1f77b4"
        ax.add_patch(patches.Rectangle(
            (x1, y1), x2 - x1, y2 - y1,
            linewidth=2, edgecolor=color, facecolor=color, alpha=0.15))
        ax.text(x1 + 2, y1 - 3, f"{conf:.2f}",
                color=color, fontsize=6, fontweight="bold",
                verticalalignment="bottom")

    for x1, y1, x2, y2 in text_boxes:
        ax.add_patch(patches.Rectangle(
            (x1, y1), x2 - x1, y2 - y1,
            linewidth=1, edgecolor="#2ca02c",
            facecolor="#2ca02c", alpha=0.06))

    ax.axis("off")
    plt.tight_layout(pad=0)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def render_diagnostic(gray, binary, blobs, font_size, text_boxes, eq_results):
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.patch.set_facecolor("#fafafa")

    titles = [
        "Grayscale", "Binary (Otsu)",
        "Blob height distribution",
        "Blobs — normal/outlier",
        f"Text regions ({len(text_boxes)})",
        f"Detections",
    ]

    axes[0, 0].imshow(gray, cmap="gray", vmin=0, vmax=255)
    axes[0, 1].imshow(binary, cmap="gray", vmin=0, vmax=1)

    heights = [b["height"] for b in blobs]
    axes[0, 2].hist(heights, bins=50, color="#1a1a1a", edgecolor="#fafafa", alpha=0.8)
    axes[0, 2].axvline(font_size, color="#d62728", linewidth=2,
                       label=f"Font = {font_size}px")
    axes[0, 2].axvline(font_size * 1.8, color="#ff7f0e", linewidth=1.5,
                       linestyle="--", label=f"Tall = {font_size*1.8:.0f}px")
    axes[0, 2].set_facecolor("#f8f8f8")
    axes[0, 2].legend(fontsize=8)
    axes[0, 2].set_xlabel("Blob height (px)", fontsize=8)
    axes[0, 2].set_ylabel("Count", fontsize=8)

    axes[1, 0].imshow(gray, cmap="gray", vmin=0, vmax=255, alpha=0.6)
    for b in blobs:
        color = ("#d62728" if b["height"] > font_size * 1.8
                 or b["width"] > font_size * 4 else "#2ca02c")
        axes[1, 0].add_patch(patches.Rectangle(
            (b["x1"], b["y1"]), b["width"], b["height"],
            linewidth=0.4, edgecolor=color, facecolor="none"))

    axes[1, 1].imshow(gray, cmap="gray", vmin=0, vmax=255)
    for x1, y1, x2, y2 in text_boxes:
        axes[1, 1].add_patch(patches.Rectangle(
            (x1, y1), x2 - x1, y2 - y1,
            linewidth=1.5, edgecolor="#2ca02c", facecolor="#2ca02c", alpha=0.15))

    axes[1, 2].imshow(gray, cmap="gray", vmin=0, vmax=255)
    for x1, y1, x2, y2 in text_boxes:
        axes[1, 2].add_patch(patches.Rectangle(
            (x1, y1), x2 - x1, y2 - y1,
            linewidth=1, edgecolor="#2ca02c", facecolor="none"))
    for det in eq_results:
        x1, y1, x2, y2 = det["box"]
        color = "#d62728" if det["class"] == 0 else "#1f77b4"
        axes[1, 2].add_patch(patches.Rectangle(
            (x1, y1), x2 - x1, y2 - y1,
            linewidth=2, edgecolor=color, facecolor=color, alpha=0.2))

    for ax, title in zip(axes.flat, titles):
        ax.set_title(title, fontsize=9, fontfamily="monospace", pad=6)
        if hasattr(ax, "axis"):
            try:
                ax.axis("off")
            except Exception:
                pass

    axes[0, 2].axis("on")
    axes[0, 2].tick_params(labelsize=7)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                facecolor="#fafafa")
    plt.close(fig)
    buf.seek(0)
    return buf


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ∂ Equation Detector")
    st.markdown("---")

    st.markdown("**Detection settings**")
    class1_threshold = st.slider(
        "Inline confidence threshold",
        min_value=0.0, max_value=1.0,
        value=0.5, step=0.05,
        help="Class 1 (inline) boxes only shown above this confidence"
    )

    debug_mode = st.checkbox("Debug mode", value=False,
                             help="Print per-region scores to terminal")

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


# ── Main ──────────────────────────────────────────────────────────────────────
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

# ── Run pipeline ──────────────────────────────────────────────────────────────
run_cca_pipeline, save_stage6 = load_pipeline()

if run_cca_pipeline is None:
    st.error(
        "Pipeline modules not found. "
        "Make sure the `pipeline/` folder is in the same directory as `app.py`."
    )
    st.stop()

with tempfile.NamedTemporaryFile(
        suffix=os.path.splitext(uploaded.name)[1], delete=False) as f:
    f.write(uploaded.read())
    tmp_path = f.name

with st.spinner("Running pipeline..."):
    try:
        gray, binary, blobs, font_size, text_boxes, eq_results = \
            run_cca_pipeline(tmp_path, debug=debug_mode)
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        os.unlink(tmp_path)
        st.stop()

# ── Metrics ───────────────────────────────────────────────────────────────────
standalone = sum(1 for d in eq_results if d["class"] == 0)
inline_all  = sum(1 for d in eq_results if d["class"] == 1)
inline_show = sum(1 for d in eq_results
                  if d["class"] == 1 and d["confidence"] >= class1_threshold)
total_show  = standalone + inline_show

doc_type_label = "dense" if any(d["class"] == 1 for d in eq_results) else "sparse"

col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    st.markdown(
        f'<div class="metric-card classtotal">'
        f'<div class="metric-value">{total_show}</div>'
        f'<div class="metric-label">Total shown</div></div>',
        unsafe_allow_html=True
    )
with col_b:
    st.markdown(
        f'<div class="metric-card class0">'
        f'<div class="metric-value">{standalone}</div>'
        f'<div class="metric-label">Standalone (class 0)</div></div>',
        unsafe_allow_html=True
    )
with col_c:
    st.markdown(
        f'<div class="metric-card class1">'
        f'<div class="metric-value">{inline_show} / {inline_all}</div>'
        f'<div class="metric-label">Inline shown / found (class 1)</div></div>',
        unsafe_allow_html=True
    )
with col_d:
    badge_cls = "badge-dense" if doc_type_label == "dense" else "badge-sparse"
    st.markdown(
        f'<div class="metric-card">'
        f'<div class="metric-value">'
        f'<span class="doc-badge {badge_cls}">{doc_type_label}</span>'
        f'</div>'
        f'<div class="metric-label">Document type</div></div>',
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Detection", "Diagnostic", "Data"])

with tab1:
    buf = render_detections(gray, text_boxes, eq_results, class1_threshold)
    st.image(buf, use_column_width=True)

    dl_col1, dl_col2 = st.columns(2)
    with dl_col1:
        st.download_button(
            "⬇ Download annotated image",
            data=buf.getvalue(),
            file_name=f"{os.path.splitext(uploaded.name)[0]}_detections.png",
            mime="image/png",
            use_container_width=True
        )

with tab2:
    with st.spinner("Rendering diagnostic..."):
        diag_buf = render_diagnostic(
            gray, binary, blobs, font_size, text_boxes, eq_results)
    st.image(diag_buf, use_column_width=True)

with tab3:
    if eq_results:
        rows = []
        for d in eq_results:
            x1, y1, x2, y2 = d["box"]
            if d["class"] == 1 and d["confidence"] < class1_threshold:
                continue
            rows.append({
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "class": d["class"],
                "confidence": d["confidence"],
                "type": "standalone" if d["class"] == 0 else "inline",
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)

        csv_bytes = df.to_csv(index=False).encode()
        st.download_button(
            "⬇ Download CSV",
            data=csv_bytes,
            file_name=f"{os.path.splitext(uploaded.name)[0]}_detections.csv",
            mime="text/csv",
            use_container_width=True
        )

        # Confidence distribution
        if len(df) > 0:
            st.markdown("**Confidence distribution**")
            fig_conf, ax_conf = plt.subplots(figsize=(8, 2.5))
            fig_conf.patch.set_facecolor("#fafafa")
            ax_conf.set_facecolor("#f8f8f8")

            class0_conf = df[df["class"] == 0]["confidence"]
            class1_conf = df[df["class"] == 1]["confidence"]

            if len(class0_conf):
                ax_conf.hist(class0_conf, bins=20, alpha=0.7,
                             color="#d62728", label="Standalone")
            if len(class1_conf):
                ax_conf.hist(class1_conf, bins=20, alpha=0.7,
                             color="#1f77b4", label="Inline")

            ax_conf.axvline(class1_threshold, color="#333",
                            linestyle="--", linewidth=1.2,
                            label=f"Threshold ({class1_threshold:.2f})")
            ax_conf.legend(fontsize=8)
            ax_conf.set_xlabel("Confidence", fontsize=8)
            ax_conf.set_ylabel("Count", fontsize=8)
            ax_conf.tick_params(labelsize=7)
            plt.tight_layout()
            st.pyplot(fig_conf)
            plt.close(fig_conf)
    else:
        st.info("No equations detected.")

# ── Cleanup ───────────────────────────────────────────────────────────────────
try:
    os.unlink(tmp_path)
except Exception:
    pass