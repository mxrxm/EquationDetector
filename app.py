# """
# app.py — Enhanced Streamlit frontend for the Equation Detector.

# Enhancements over original:
#   - Refined dark-theme UI with sharp editorial aesthetics (JetBrains Mono + Syne)
#   - Animated header, glowing metric cards, polished sidebar
#   - NEW: "Crops" tab — extracts every standalone equation as a cropped image
#   - Individual per-crop download buttons + "Download All as ZIP" bundle
#   - Inline crops gallery with confidence badges
#   - detector_mode radio wired into run_cca_pipeline()
#   - doc_type_label read from pipeline output
#   - use_container_width replaces deprecated use_column_width
#   - diagnostic render cached separately (no re-run on slider move)
#   - pipeline result cached with st.session_state keyed on filename+mode
# """

# import os
# import sys
# import tempfile
# import io
# import zipfile

# import streamlit as st
# import matplotlib
# matplotlib.use("Agg")
# import matplotlib.pyplot as plt
# import matplotlib.patches as patches
# from PIL import Image

# # ── Page config ───────────────────────────────────────────────────────────────
# st.set_page_config(
#     page_title="EqDetect · Equation Detector",
#     page_icon="∂",
#     layout="wide",
#     initial_sidebar_state="expanded",
# )

# # ── CSS ───────────────────────────────────────────────────────────────────────
# st.markdown("""
# <style>
# @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@300;400;500;700&display=swap');

# /* ── Base ── */
# html, body, [class*="css"] {
#     font-family: 'JetBrains Mono', monospace;
#     background-color: #111114;
#     color: #e8e6e0;
# }
# .stApp { background: #111114; }
# section[data-testid="stMain"] > div { background: #111114; }

# /* ── Main content padding ── */
# section[data-testid="stMain"] .block-container {
#     padding-top: 3rem;
#     padding-left: 3rem;
#     padding-right: 3rem;
#     max-width: 100%;
# }

# /* ══════════════════════════════════
#    SIDEBAR
# ══════════════════════════════════ */
# div[data-testid="stSidebar"] {
#     background: #0d0d0f !important;
#     border-right: 1px solid #1c1c20;
#     min-width: 260px !important;
#     max-width: 260px !important;
# }
# div[data-testid="stSidebar"] * {
#     font-family: 'JetBrains Mono', monospace !important;
# }
# /* Sidebar top logo area */
# .sb-logo {
#     display: flex;
#     align-items: center;
#     gap: 0.5rem;
#     padding: 0.2rem 0 0.1rem;
# }
# .sb-logo-icon {
#     font-size: 1.1rem;
#     color: #e8583a;
#     font-family: 'Syne', sans-serif !important;
#     font-weight: 800;
#     line-height: 1;
# }
# .sb-logo-name {
#     font-family: 'Syne', sans-serif !important;
#     font-size: 1rem;
#     font-weight: 700;
#     color: #f0ede6;
#     letter-spacing: -0.02em;
# }
# .sb-version {
#     font-size: 0.58rem;
#     letter-spacing: 0.2em;
#     text-transform: uppercase;
#     color: #383838;
#     margin-top: 0.1rem;
#     margin-bottom: 0.8rem;
# }
# /* Section headers */
# .sb-section {
#     font-size: 0.58rem;
#     letter-spacing: 0.2em;
#     text-transform: uppercase;
#     color: #383838;
#     padding-bottom: 0.35rem;
#     border-bottom: 1px solid #1c1c20;
#     margin-bottom: 0.7rem;
#     margin-top: 1.1rem;
# }
# /* Sidebar controls */
# [data-testid="stRadio"] label {
#     font-size: 0.8rem !important;
#     color: #ccc !important;
# }
# [data-testid="stRadio"] [data-baseweb="radio"] svg { color: #e8583a !important; }
# [data-testid="stCheckbox"] label { font-size: 0.8rem !important; color: #ccc !important; }
# [data-testid="stSlider"] label   { font-size: 0.75rem !important; color: #888 !important; }
# /* Selected slider value */
# [data-testid="stSlider"] [data-testid="stMarkdownContainer"] p {
#     color: #e8583a !important;
#     font-size: 0.78rem !important;
# }
# /* Slider track accent */
# [data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
#     background: #e8583a !important;
#     border-color: #e8583a !important;
# }
# /* Legend dots */
# .sb-legend { line-height: 2.1; font-size: 0.78rem; color: #888; }
# .sb-dot {
#     display: inline-block;
#     width: 8px; height: 8px;
#     border-radius: 50%;
#     margin-right: 0.5rem;
#     vertical-align: middle;
# }
# /* Footer */
# .sb-footer {
#     font-size: 0.58rem;
#     color: #2e2e2e;
#     letter-spacing: 0.06em;
#     margin-top: 0.5rem;
# }
# /* Expander */
# [data-testid="stExpander"] {
#     background: #131316 !important;
#     border: 1px solid #1c1c20 !important;
#     border-radius: 3px !important;
# }
# [data-testid="stExpander"] summary {
#     font-size: 0.75rem !important;
#     color: #888 !important;
# }

# /* ══════════════════════════════════
#    HEADER — centered
# ══════════════════════════════════ */
# .eq-hero {
#     text-align: center;
#     padding: 2.5rem 0 0.5rem;
#     margin-bottom: 0.5rem;
# }
# .eq-title {
#     font-family: 'Syne', sans-serif;
#     font-size: 3.4rem;
#     font-weight: 800;
#     letter-spacing: -0.04em;
#     color: #f0ede6;
#     line-height: 1;
#     margin: 0;
# }
# .eq-title-accent { color: #e8583a; }
# .eq-subtitle {
#     font-family: 'JetBrains Mono', monospace;
#     font-size: 0.65rem;
#     color: #444;
#     letter-spacing: 0.2em;
#     text-transform: uppercase;
#     margin-top: 0.9rem;
# }

# /* ══════════════════════════════════
#    UPLOAD ZONE — centered dashed card
# ══════════════════════════════════ */
# .upload-wrapper {
#     max-width: 720px;
#     margin: 1.5rem auto 0.5rem;
#     border: 1.5px dashed #2e2e34;
#     border-radius: 6px;
#     padding: 2.2rem 2rem 1.8rem;
#     background: transparent;
#     transition: border-color 0.2s;
# }
# .upload-wrapper:hover { border-color: #e8583a66; }
# /* Override Streamlit's own uploader chrome inside our wrapper */
# [data-testid="stFileUploader"] {
#     background: transparent !important;
#     border: none !important;
#     padding: 0 !important;
# }
# [data-testid="stFileUploaderDropzone"] {
#     background: #18181c !important;
#     border: 1px solid #242428 !important;
#     border-radius: 4px !important;
# }
# .upload-hint {
#     text-align: center;
#     font-size: 0.78rem;
#     color: #555;
#     margin-top: 0.9rem;
#     letter-spacing: 0.03em;
# }
# .upload-hint span { color: #e8583a; margin-right: 0.35rem; }

# /* ══════════════════════════════════
#    METRIC CARDS
# ══════════════════════════════════ */
# .badge {
#     display: inline-block;
#     font-family: 'JetBrains Mono', monospace;
#     font-size: 0.68rem;
#     font-weight: 700;
#     letter-spacing: 0.12em;
#     text-transform: uppercase;
#     padding: 0.25rem 0.7rem;
#     border-radius: 2px;
# }
# .badge-dense  { background: #e8583a22; color: #e8583a; border: 1px solid #e8583a55; }
# .badge-sparse { background: #4f9cf922; color: #4f9cf9; border: 1px solid #4f9cf955; }

# /* ══════════════════════════════════
#    TABS
# ══════════════════════════════════ */
# [data-testid="stTabs"] [data-baseweb="tab-list"] {
#     background: transparent;
#     border-bottom: 1px solid #1e1e22;
#     gap: 0;
# }
# [data-testid="stTabs"] [data-baseweb="tab"] {
#     font-family: 'JetBrains Mono', monospace;
#     font-size: 0.72rem;
#     letter-spacing: 0.12em;
#     text-transform: uppercase;
#     color: #444;
#     padding: 0.75rem 1.5rem;
#     background: transparent;
#     border: none;
#     border-bottom: 2px solid transparent;
#     transition: color 0.15s;
# }
# [data-testid="stTabs"] [aria-selected="true"] {
#     color: #e8583a !important;
#     border-bottom-color: #e8583a !important;
# }

# /* ══════════════════════════════════
#    BUTTONS
# ══════════════════════════════════ */
# .stButton > button,
# [data-testid="stDownloadButton"] > button {
#     font-family: 'JetBrains Mono', monospace;
#     font-size: 0.72rem;
#     letter-spacing: 0.05em;
#     background: #1a1a1e;
#     color: #d0cec8;
#     border: 1px solid #2a2a2e;
#     border-radius: 3px;
#     padding: 0.5rem 1.2rem;
#     transition: all 0.15s;
# }
# .stButton > button:hover,
# [data-testid="stDownloadButton"] > button:hover {
#     background: #e8583a;
#     border-color: #e8583a;
#     color: #fff;
# }

# /* ══════════════════════════════════
#    MISC
# ══════════════════════════════════ */
# [data-testid="stAlert"] {
#     background: #131316;
#     border: 1px solid #222;
#     border-radius: 4px;
#     font-size: 0.78rem;
# }
# [data-testid="stDataFrame"] {
#     border: 1px solid #222;
#     border-radius: 4px;
#     font-size: 0.78rem;
# }
# hr { border-color: #1e1e22; }
# [data-testid="stSpinner"] { color: #e8583a; }
# .conf-badge {
#     display: inline-block;
#     font-size: 0.58rem;
#     font-weight: 700;
#     letter-spacing: 0.08em;
#     padding: 0.12rem 0.45rem;
#     border-radius: 2px;
#     background: #e8583a1a;
#     color: #e8583a;
#     border: 1px solid #e8583a33;
#     margin-left: 0.4rem;
# }
# </style>
# """, unsafe_allow_html=True)


# # ── Helpers ───────────────────────────────────────────────────────────────────
# def _fig_bytes(fig, dpi=150):
#     buf = io.BytesIO()
#     fig.savefig(buf, format="png", dpi=dpi,
#                 bbox_inches="tight", facecolor=fig.get_facecolor())
#     plt.close(fig)
#     buf.seek(0)
#     return buf.getvalue()


# def _pil_to_png_bytes(img):
#     buf = io.BytesIO()
#     img.save(buf, format="PNG")
#     buf.seek(0)
#     return buf.getvalue()


# def _render_detections(gray, text_boxes, eq_results, class1_threshold):
#     fig, ax = plt.subplots(figsize=(12, 16))
#     fig.patch.set_facecolor("#0d0d0f")
#     ax.set_facecolor("#0d0d0f")
#     ax.imshow(gray, cmap="gray", vmin=0, vmax=255)

#     for x1, y1, x2, y2 in text_boxes:
#         ax.add_patch(patches.Rectangle(
#             (x1, y1), x2-x1, y2-y1,
#             linewidth=0.8, edgecolor="#4ade80",
#             facecolor="#4ade80", alpha=0.06))

#     for det in eq_results:
#         x1, y1, x2, y2 = det["box"]
#         cls, conf = det["class"], det["confidence"]
#         if cls == 1 and conf < class1_threshold:
#             continue
#         color = "#e8583a" if cls == 0 else "#4f9cf9"
#         ax.add_patch(patches.Rectangle(
#             (x1, y1), x2-x1, y2-y1,
#             linewidth=2, edgecolor=color, facecolor=color, alpha=0.12))
#         ax.add_patch(patches.Rectangle(
#             (x1, y1), x2-x1, y2-y1,
#             linewidth=2, edgecolor=color, facecolor="none"))
#         ax.text(x1+3, y1-4, f"{conf:.2f}",
#                 color=color, fontsize=6.5, fontweight="bold",
#                 fontfamily="monospace", verticalalignment="bottom")

#     ax.axis("off")
#     plt.tight_layout(pad=0)
#     return fig


# @st.cache_data(show_spinner=False)
# def _render_diagnostic_cached(gray_key, gray_flat, binary_flat, blob_data,
#                                font_size, text_boxes, eq_results,
#                                img_width, img_height):
#     gray   = [list(gray_flat  [r*img_width:(r+1)*img_width]) for r in range(img_height)]
#     binary = [list(binary_flat[r*img_width:(r+1)*img_width]) for r in range(img_height)]

#     blob_data  = [{"x1": t[0], "y1": t[1], "x2": t[2], "y2": t[3],
#                    "height": t[4], "width": t[5], "area": t[6], "fill_ratio": t[7]}
#                   for t in blob_data]
#     eq_results = [{"box": t[0], "confidence": t[1], "class": t[2]}
#                   for t in eq_results]

#     BG = "#0d0d0f"
#     PANEL = "#131316"

#     fig, axes = plt.subplots(2, 3, figsize=(20, 13))
#     fig.patch.set_facecolor(BG)
#     fig.suptitle("pipeline diagnostic", fontsize=11,
#                  fontfamily="monospace", y=1.01, color="#555")

#     standalone = [d for d in eq_results if d["class"] == 0]
#     inline     = [d for d in eq_results if d["class"] == 1]

#     def _style(ax, title):
#         ax.set_facecolor(PANEL)
#         ax.set_title(title, fontsize=8, fontfamily="monospace", color="#666", pad=6)
#         ax.axis("off")
#         for spine in ax.spines.values():
#             spine.set_edgecolor("#222")

#     axes[0,0].imshow(gray,   cmap="gray", vmin=0, vmax=255)
#     _style(axes[0,0], "01 · grayscale input")

#     axes[0,1].imshow(binary, cmap="gray", vmin=0, vmax=1)
#     _style(axes[0,1], "02 · binary (adaptive otsu)")

#     heights = [b["height"] for b in blob_data]
#     axes[0,2].set_facecolor(PANEL)
#     axes[0,2].hist(heights, bins=55, color="#e8583a", edgecolor=BG, alpha=0.9)
#     axes[0,2].axvline(font_size,        color="#f0ede6", lw=1.5,
#                       label=f"font={font_size}px")
#     axes[0,2].axvline(font_size * 1.9,  color="#4f9cf9", lw=1.2, ls="--",
#                       label=f"tall={font_size*1.9:.0f}px")
#     axes[0,2].axvline(font_size * 0.42, color="#a78bfa", lw=1.2, ls=":",
#                       label=f"tiny={font_size*0.42:.0f}px")
#     axes[0,2].legend(fontsize=7, facecolor=BG, edgecolor="#333",
#                      labelcolor="#aaa")
#     axes[0,2].set_xlabel("blob height (px)", fontsize=7, color="#555")
#     axes[0,2].set_ylabel("count", fontsize=7, color="#555")
#     axes[0,2].set_title("03 · blob height distribution", fontsize=8,
#                          fontfamily="monospace", color="#666", pad=6)
#     axes[0,2].tick_params(labelsize=6, colors="#444")
#     for spine in axes[0,2].spines.values():
#         spine.set_edgecolor("#222")

#     axes[1,0].imshow(gray, cmap="gray", vmin=0, vmax=255, alpha=0.5)
#     for b in blob_data:
#         is_out = (b["height"] > font_size * 1.9 or
#                   (b["width"] > font_size * 4 and b["height"] < font_size * 0.5))
#         color = "#e8583a" if is_out else "#4ade80"
#         axes[1,0].add_patch(patches.Rectangle(
#             (b["x1"], b["y1"]), b["width"], b["height"],
#             linewidth=1.0 if is_out else 0.4,
#             edgecolor=color, facecolor="none",
#             alpha=0.9 if is_out else 0.5))
#     _style(axes[1,0], "04 · blob map  ·  green=normal  red=outlier")
#     axes[1,0].set_visible(True)
#     axes[1,0].axis("off")

#     axes[1,1].imshow(gray, cmap="gray", vmin=0, vmax=255)
#     for x1, y1, x2, y2 in text_boxes:
#         axes[1,1].add_patch(patches.Rectangle(
#             (x1, y1), x2-x1, y2-y1,
#             linewidth=1.2, edgecolor="#4ade80", facecolor="#4ade80", alpha=0.12))
#     _style(axes[1,1], f"05 · text regions ({len(text_boxes)})")
#     axes[1,1].axis("off")

#     axes[1,2].imshow(gray, cmap="gray", vmin=0, vmax=255)
#     for x1, y1, x2, y2 in text_boxes:
#         axes[1,2].add_patch(patches.Rectangle(
#             (x1, y1), x2-x1, y2-y1,
#             linewidth=0.8, edgecolor="#4ade80", facecolor="none"))
#     for det in standalone:
#         x1, y1, x2, y2 = det["box"]
#         axes[1,2].add_patch(patches.Rectangle(
#             (x1, y1), x2-x1, y2-y1,
#             linewidth=1.8, edgecolor="#e8583a", facecolor="#e8583a", alpha=0.15))
#         axes[1,2].text(x1+2, y1-3, f"{det['confidence']:.2f}",
#                        color="#e8583a", fontsize=5, fontweight="bold")
#     for det in inline:
#         x1, y1, x2, y2 = det["box"]
#         axes[1,2].add_patch(patches.Rectangle(
#             (x1, y1), x2-x1, y2-y1,
#             linewidth=1.8, edgecolor="#4f9cf9", facecolor="#4f9cf9", alpha=0.15))
#         axes[1,2].text(x1+2, y1-3, f"{det['confidence']:.2f}",
#                        color="#4f9cf9", fontsize=5, fontweight="bold")
#     _style(axes[1,2],
#            f"06 · detections · red={len(standalone)} standalone · blue={len(inline)} inline")
#     axes[1,2].axis("off")

#     plt.tight_layout()
#     return _fig_bytes(fig, dpi=120)


# @st.cache_resource
# def _load_pipeline():
#     try:
#         from pipeline.pipeline import run_cca_pipeline
#         return run_cca_pipeline
#     except ImportError:
#         return None


# # ══════════════════════════════════════════════════════════════════════════════
# # SIDEBAR
# # ══════════════════════════════════════════════════════════════════════════════
# with st.sidebar:
#     # ── Logo ──
#     st.markdown("""
#     <div class="sb-logo">
#       <span class="sb-logo-icon">∂</span>
#       <span class="sb-logo-name">EqDetect</span>
#     </div>
#     <div class="sb-version">Equation Detector V2</div>
#     """, unsafe_allow_html=True)

#     st.markdown("<hr style='border-color:#1c1c20;margin:0 0 0.2rem'>", unsafe_allow_html=True)

#     # ── Detection section ──
#     st.markdown("<div class='sb-section'>Detection</div>", unsafe_allow_html=True)
#     detector_mode = st.radio(
#         "Mode",
#         options=["combined", "blob", "edge"],
#         index=0,
#         help=(
#             "combined — blob + edge consensus (most robust)\n"
#             "blob     — ink density + body-blob ratio\n"
#             "edge     — Sobel edge density"
#         )
#     )

#     class1_threshold = st.slider(
#         "Inline confidence threshold",
#         min_value=0.0, max_value=1.0,
#         value=0.25, step=0.05,
#     )

#     with st.expander("⚙ Inline tuning"):
#         inline_score_threshold = st.slider(
#             "Score threshold", min_value=2.0, max_value=6.0, value=4.2, step=0.1)
#         inline_delta_threshold = st.slider(
#             "Baseline delta", min_value=3.0, max_value=8.0, value=6.0, step=0.1)
#         inline_gap_factor = st.slider(
#             "Cluster gap factor", min_value=0.7, max_value=1.3, value=1.0, step=0.05)
#         inline_max_cluster_size = st.slider(
#             "Max cluster size", min_value=12, max_value=40, value=28, step=2)
#         inline_sentence_min_n = st.slider(
#             "Sentence min blobs", min_value=8, max_value=24, value=12, step=1)
#         inline_tiny_height_ratio = st.slider(
#             "Tiny height ratio", min_value=0.30, max_value=0.55, value=0.42, step=0.01)
#         inline_frac_width_ratio = st.slider(
#             "Fraction width ratio", min_value=0.9, max_value=2.0, value=1.2, step=0.05)
#         inline_frac_height_ratio = st.slider(
#             "Fraction height ratio", min_value=0.08, max_value=0.25, value=0.15, step=0.01)
#         inline_tall_height_ratio = st.slider(
#             "Tall height ratio", min_value=1.4, max_value=2.6, value=1.9, step=0.05)
#         inline_baseline_max = st.slider(
#             "Baseline max", min_value=0.5, max_value=2.5, value=1.5, step=0.1)

#     debug_mode = st.checkbox("Debug mode", value=False)

#     # ── Legend ──
#     st.markdown("<hr style='border-color:#1c1c20;margin:1rem 0 0'>", unsafe_allow_html=True)
#     st.markdown("<div class='sb-section'>Legend</div>", unsafe_allow_html=True)
#     st.markdown("""
#     <div class="sb-legend">
#       <div><span class="sb-dot" style="background:#e8583a"></span>Standalone equation</div>
#       <div><span class="sb-dot" style="background:#4f9cf9"></span>Inline equation</div>
#       <div><span class="sb-dot" style="background:#4ade80"></span>Text region</div>
#     </div>
#     """, unsafe_allow_html=True)

#     # ── Footer ──
#     st.markdown("<hr style='border-color:#1c1c20;margin:1rem 0 0.5rem'>", unsafe_allow_html=True)
#     st.markdown(
#         "<div class='sb-footer'>No OpenCV · No NumPy · Pure Python CCA</div>",
#         unsafe_allow_html=True
#     )


# # ══════════════════════════════════════════════════════════════════════════════
# # HEADER — centered
# # ══════════════════════════════════════════════════════════════════════════════
# st.markdown("""
# <div class="eq-hero">
#   <div class="eq-title">Eq<span class="eq-title-accent">Detect</span></div>
#   <div class="eq-subtitle">Mathematical Expression Localization &nbsp;·&nbsp; Connected Component Analysis</div>
# </div>
# """, unsafe_allow_html=True)

# # ── Upload zone — centered dashed card ────────────────────────────────────────
# # We wrap the Streamlit uploader in a centered div via columns trick
# _l, _c, _r = st.columns([1, 3, 1])
# with _c:
#     uploaded = st.file_uploader(
#         "Drop a document image — research paper, textbook, or assignment sheet",
#         type=["png", "jpg", "jpeg"],
#         label_visibility="visible"
#     )

# if uploaded is None:
#     _l2, _c2, _r2 = st.columns([1, 3, 1])
#     with _c2:
#         st.markdown(
#             "<div class='upload-hint'>"
#             "<span>↑</span>Upload a document image to begin detection."
#             "</div>",
#             unsafe_allow_html=True
#         )
#     st.stop()


# # ══════════════════════════════════════════════════════════════════════════════
# # PIPELINE
# # ══════════════════════════════════════════════════════════════════════════════
# run_cca_pipeline = _load_pipeline()
# if run_cca_pipeline is None:
#     st.error("Pipeline modules not found. Ensure the `pipeline/` folder is alongside `app.py`.")
#     st.stop()

# _cache_key = (
#     f"{uploaded.name}_{uploaded.size}_{detector_mode}_"
#     f"{inline_score_threshold}_{inline_delta_threshold}_"
#     f"{inline_gap_factor}_{inline_max_cluster_size}_"
#     f"{inline_sentence_min_n}_{inline_tiny_height_ratio}_"
#     f"{inline_frac_width_ratio}_{inline_frac_height_ratio}_"
#     f"{inline_tall_height_ratio}_{inline_baseline_max}"
# )

# if st.session_state.get("_cache_key") != _cache_key:
#     suffix = os.path.splitext(uploaded.name)[1] or ".png"
#     with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
#         f.write(uploaded.getvalue())
#         tmp_path = f.name

#     with st.spinner("Running pipeline…"):
#         try:
#             gray, binary, blobs, font_size, text_boxes, eq_results = \
#                 run_cca_pipeline(
#                     tmp_path,
#                     detector_mode=detector_mode,
#                     inline_score_threshold=inline_score_threshold,
#                     inline_delta_threshold=inline_delta_threshold,
#                     inline_gap_factor=inline_gap_factor,
#                     inline_max_cluster_size=inline_max_cluster_size,
#                     inline_sentence_min_n=inline_sentence_min_n,
#                     inline_tiny_height_ratio=inline_tiny_height_ratio,
#                     inline_frac_width_ratio=inline_frac_width_ratio,
#                     inline_frac_height_ratio=inline_frac_height_ratio,
#                     inline_tall_height_ratio=inline_tall_height_ratio,
#                     inline_baseline_max=inline_baseline_max,
#                     debug=debug_mode,
#                 )
#         except Exception as e:
#             st.error(f"Pipeline error: {e}")
#             try:
#                 os.unlink(tmp_path)
#             except Exception:
#                 pass
#             st.stop()
#         finally:
#             try:
#                 os.unlink(tmp_path)
#             except Exception:
#                 pass

#     has_inline = any(d["class"] == 1 for d in eq_results)
#     doc_type   = "dense" if has_inline else "sparse"

#     st.session_state["_cache_key"]  = _cache_key
#     st.session_state["gray"]        = gray
#     st.session_state["binary"]      = binary
#     st.session_state["blobs"]       = blobs
#     st.session_state["font_size"]   = font_size
#     st.session_state["text_boxes"]  = text_boxes
#     st.session_state["eq_results"]  = eq_results
#     st.session_state["doc_type"]    = doc_type

# gray       = st.session_state["gray"]
# binary     = st.session_state["binary"]
# blobs      = st.session_state["blobs"]
# font_size  = st.session_state["font_size"]
# text_boxes = st.session_state["text_boxes"]
# eq_results = st.session_state["eq_results"]
# doc_type   = st.session_state["doc_type"]


# # ══════════════════════════════════════════════════════════════════════════════
# # METRICS
# # ══════════════════════════════════════════════════════════════════════════════
# standalone_all  = [d for d in eq_results if d["class"] == 0]
# inline_all      = [d for d in eq_results if d["class"] == 1]
# inline_shown    = [d for d in inline_all if d["confidence"] >= class1_threshold]
# total_shown     = len(standalone_all) + len(inline_shown)

# badge_cls = "badge-dense" if doc_type == "dense" else "badge-sparse"
# inline_value = f'{len(inline_shown)}<span style="font-size:1rem;color:#3a3a3a"> / {len(inline_all)}</span>'

# st.markdown(f"""
# <div style="display:flex; gap:0.75rem; flex-wrap:wrap; margin-bottom:0.5rem;">

#   <div style="
#       flex: 0 0 auto; width:180px;
#       background:#131316; border:1px solid #222; border-radius:4px;
#       border-top:2px solid #4ade80; padding:1.1rem 1.3rem;">
#     <div style="font-family:'Syne',sans-serif;font-size:2.2rem;font-weight:800;
#                 color:#f0ede6;line-height:1;letter-spacing:-0.03em;">
#       {total_shown}
#     </div>
#     <div style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;
#                 color:#555;text-transform:uppercase;letter-spacing:0.12em;
#                 margin-top:0.45rem;">
#       Total detected
#     </div>
#   </div>

#   <div style="
#       flex: 0 0 auto; width:180px;
#       background:#131316; border:1px solid #222; border-radius:4px;
#       border-top:2px solid #e8583a; padding:1.1rem 1.3rem;">
#     <div style="font-family:'Syne',sans-serif;font-size:2.2rem;font-weight:800;
#                 color:#f0ede6;line-height:1;letter-spacing:-0.03em;">
#       {len(standalone_all)}
#     </div>
#     <div style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;
#                 color:#555;text-transform:uppercase;letter-spacing:0.12em;
#                 margin-top:0.45rem;">
#       Standalone (class 0)
#     </div>
#   </div>

#   <div style="
#       flex: 0 0 auto; width:200px;
#       background:#131316; border:1px solid #222; border-radius:4px;
#       border-top:2px solid #4f9cf9; padding:1.1rem 1.3rem;">
#     <div style="font-family:'Syne',sans-serif;font-size:2.2rem;font-weight:800;
#                 color:#f0ede6;line-height:1;letter-spacing:-0.03em;">
#       {inline_value}
#     </div>
#     <div style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;
#                 color:#555;text-transform:uppercase;letter-spacing:0.12em;
#                 margin-top:0.45rem;">
#       Inline shown / found
#     </div>
#   </div>

#   <div style="
#       flex: 0 0 auto; width:160px;
#       background:#131316; border:1px solid #222; border-radius:4px;
#       border-top:2px solid #a78bfa; padding:1.1rem 1.3rem;">
#     <div style="font-family:'Syne',sans-serif;font-size:1.1rem;font-weight:800;
#                 color:#f0ede6;line-height:1;letter-spacing:-0.01em;
#                 margin-top:0.3rem;">
#       <span class="badge {badge_cls}">{doc_type}</span>
#     </div>
#     <div style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;
#                 color:#555;text-transform:uppercase;letter-spacing:0.12em;
#                 margin-top:0.75rem;">
#       Document type
#     </div>
#   </div>

# </div>
# """, unsafe_allow_html=True)

# st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)


# # ══════════════════════════════════════════════════════════════════════════════
# # TABS
# # ══════════════════════════════════════════════════════════════════════════════
# tab1, tab2, tab3, tab4 = st.tabs(["Detection", "Crops", "Diagnostic", "Data"])


# # ── Tab 1: Detection overlay ──────────────────────────────────────────────────
# with tab1:
#     det_fig  = _render_detections(gray, text_boxes, eq_results, class1_threshold)
#     det_data = _fig_bytes(det_fig, dpi=150)

#     st.image(det_data, use_container_width=True)

#     st.download_button(
#         "⬇  Download annotated image",
#         data=det_data,
#         file_name=f"{os.path.splitext(uploaded.name)[0]}_detections.png",
#         mime="image/png",
#         use_container_width=True,
#     )


# # ── Tab 2: Equation Crops ─────────────────────────────────────────────────────
# with tab2:
#     try:
#         from pipeline.crop_equations import crop_standalone
#         _crop_module_ok = True
#     except ImportError:
#         _crop_module_ok = False

#     standalone_dets = [d for d in eq_results if d["class"] == 0]

#     if not standalone_dets:
#         st.info("No standalone equations detected — nothing to crop.")
#     elif not _crop_module_ok:
#         st.error("crop_equations module not found. Add `pipeline/crop_equations.py`.")
#     else:
#         crops = crop_standalone(gray, eq_results, padding=10)
#         standalone_sorted = crops  # already sorted top-to-bottom by the module

#         st.markdown(
#             f"<div style='font-size:0.7rem;color:#555;letter-spacing:0.1em;"
#             f"text-transform:uppercase;margin-bottom:1.2rem'>"
#             f"{len(crops)} standalone equation{'s' if len(crops)!=1 else ''} extracted"
#             f"</div>",
#             unsafe_allow_html=True
#         )

#         # ── Build ZIP in memory ────────────────────────────────────────────
#         zip_buf = io.BytesIO()
#         crop_pngs = []   # list of (filename, png_bytes, confidence)

#         with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
#             for c in crops:
#                 png_bytes = _pil_to_png_bytes(c["image"])
#                 fname     = f"eq_{c['index']:03d}_conf{c['confidence']:.2f}.png"
#                 crop_pngs.append((fname, png_bytes, c["confidence"]))
#                 zf.writestr(fname, png_bytes)

#         zip_buf.seek(0)

#         st.download_button(
#             f"⬇  Download all {len(crops)} crops as ZIP",
#             data=zip_buf.getvalue(),
#             file_name=f"{os.path.splitext(uploaded.name)[0]}_crops.zip",
#             mime="application/zip",
#             use_container_width=True,
#         )

#         st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

#         # ── Gallery: 3 columns ─────────────────────────────────────────────
#         cols_per_row = 3
#         rows_needed  = (len(crop_pngs) + cols_per_row - 1) // cols_per_row

#         for row_i in range(rows_needed):
#             cols = st.columns(cols_per_row)
#             for col_i, col in enumerate(cols):
#                 idx = row_i * cols_per_row + col_i
#                 if idx >= len(crop_pngs):
#                     break
#                 fname, png_bytes, conf = crop_pngs[idx]
#                 eq_num = idx + 1
#                 with col:
#                     st.markdown(
#                         f"<div style='font-size:0.6rem;color:#555;"
#                         f"letter-spacing:0.1em;text-transform:uppercase;"
#                         f"margin-bottom:0.3rem'>"
#                         f"EQ·{eq_num:03d}"
#                         f"<span class='conf-badge'>conf {conf:.2f}</span>"
#                         f"</div>",
#                         unsafe_allow_html=True
#                     )
#                     st.image(png_bytes, use_container_width=True)
#                     st.download_button(
#                         f"⬇ Save",
#                         data=png_bytes,
#                         file_name=fname,
#                         mime="image/png",
#                         key=f"crop_dl_{idx}",
#                         use_container_width=True,
#                     )
#                     st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)


# # ── Tab 3: Diagnostic ─────────────────────────────────────────────────────────
# with tab3:
#     img_height = len(gray)
#     img_width  = len(gray[0])

#     gray_flat   = tuple(v for row in gray   for v in row)
#     binary_flat = tuple(v for row in binary for v in row)

#     diag_data = _render_diagnostic_cached(
#         _cache_key,
#         gray_flat, binary_flat,
#         tuple(
#             (b["x1"], b["y1"], b["x2"], b["y2"],
#              b["height"], b["width"], b["area"],
#              b.get("fill_ratio", 0))
#             for b in blobs
#         ),
#         font_size,
#         tuple(text_boxes),
#         tuple(
#             (d["box"], d["confidence"], d["class"])
#             for d in eq_results
#         ),
#         img_width, img_height,
#     )
#     st.image(diag_data, use_container_width=True)

#     st.download_button(
#         "⬇  Download diagnostic image",
#         data=diag_data,
#         file_name=f"{os.path.splitext(uploaded.name)[0]}_diagnostic.png",
#         mime="image/png",
#         use_container_width=True,
#     )


# # ── Tab 4: Data table + histogram + CSV ───────────────────────────────────────
# with tab4:
#     rows = []
#     for d in eq_results:
#         x1, y1, x2, y2 = d["box"]
#         cls, conf = d["class"], d["confidence"]
#         if cls == 1 and conf < class1_threshold:
#             continue
#         rows.append({
#             "x1":         x1, "y1": y1, "x2": x2, "y2": y2,
#             "class":      cls,
#             "type":       "standalone" if cls == 0 else "inline",
#             "confidence": round(conf, 4),
#             "width_px":   x2 - x1,
#             "height_px":  y2 - y1,
#         })

#     if rows:
#         try:
#             import pandas as pd
#             df = pd.DataFrame(rows)
#             st.dataframe(df, use_container_width=True)

#             st.markdown(
#                 "<div style='font-size:0.7rem;color:#555;letter-spacing:0.1em;"
#                 "text-transform:uppercase;margin:1rem 0 0.5rem'>Confidence by class</div>",
#                 unsafe_allow_html=True
#             )
#             st.dataframe(
#                 df.groupby("type")["confidence"].describe().round(3),
#                 use_container_width=True,
#             )
#             csv_bytes = df.to_csv(index=False).encode()

#         except ImportError:
#             st.write(rows)
#             import csv, io as _io
#             buf = _io.StringIO()
#             writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
#             writer.writeheader()
#             writer.writerows(rows)
#             csv_bytes = buf.getvalue().encode()

#         st.download_button(
#             "⬇  Download CSV",
#             data=csv_bytes,
#             file_name=f"{os.path.splitext(uploaded.name)[0]}_detections.csv",
#             mime="text/csv",
#             use_container_width=True,
#         )

#         st.markdown(
#             "<div style='font-size:0.7rem;color:#555;letter-spacing:0.1em;"
#             "text-transform:uppercase;margin:1.5rem 0 0.5rem'>Confidence distribution</div>",
#             unsafe_allow_html=True
#         )

#         fig_conf, ax_conf = plt.subplots(figsize=(8, 2.8))
#         fig_conf.patch.set_facecolor("#0d0d0f")
#         ax_conf.set_facecolor("#131316")

#         c0 = [d["confidence"] for d in eq_results if d["class"] == 0]
#         c1 = [d["confidence"] for d in eq_results
#               if d["class"] == 1 and d["confidence"] >= class1_threshold]

#         if c0:
#             ax_conf.hist(c0, bins=20, alpha=0.85, color="#e8583a",
#                          label=f"Standalone ({len(c0)})", edgecolor="#0d0d0f")
#         if c1:
#             ax_conf.hist(c1, bins=20, alpha=0.85, color="#4f9cf9",
#                          label=f"Inline ({len(c1)})", edgecolor="#0d0d0f")

#         ax_conf.axvline(class1_threshold, color="#f0ede6", ls="--", lw=1,
#                         label=f"Threshold ({class1_threshold:.2f})")
#         ax_conf.legend(fontsize=7, facecolor="#131316",
#                        edgecolor="#333", labelcolor="#aaa")
#         ax_conf.set_xlabel("Confidence", fontsize=7, color="#555")
#         ax_conf.set_ylabel("Count", fontsize=7, color="#555")
#         ax_conf.tick_params(labelsize=6, colors="#444")
#         for spine in ax_conf.spines.values():
#             spine.set_edgecolor("#222")
#         plt.tight_layout()
#         st.pyplot(fig_conf)
#         plt.close(fig_conf)

#     else:
#         st.info("No equations detected above the current threshold.")


"""
app.py — Enhanced Streamlit frontend for the Equation Detector.

Enhancements over original:
  - Refined dark-theme UI with sharp editorial aesthetics (JetBrains Mono + Syne)
  - Animated header, glowing metric cards, polished sidebar
  - NEW: "Crops" tab — extracts every standalone equation as a cropped image
  - Individual per-crop download buttons + "Download All as ZIP" bundle
  - Inline crops gallery with confidence badges
  - doc_type_label read from pipeline output
  - use_container_width replaces deprecated use_column_width
  - diagnostic render cached separately (no re-run on slider move)
  - pipeline result cached with st.session_state keyed on filename
"""

import os
import sys
import tempfile
import io
import zipfile

import streamlit as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="EqDetect · Equation Detector",
    page_icon="∂",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@300;400;500;700&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'JetBrains Mono', monospace;
    background-color: #111114;
    color: #e8e6e0;
}
.stApp { background: #111114; }
section[data-testid="stMain"] > div { background: #111114; }

/* ── Main content padding ── */
section[data-testid="stMain"] .block-container {
    padding-top: 3rem;
    padding-left: 3rem;
    padding-right: 3rem;
    max-width: 100%;
}

/* ══════════════════════════════════
   SIDEBAR
══════════════════════════════════ */
div[data-testid="stSidebar"] {
    background: #0d0d0f !important;
    border-right: 1px solid #1c1c20;
    min-width: 260px !important;
    max-width: 260px !important;
}
div[data-testid="stSidebar"] * {
    font-family: 'JetBrains Mono', monospace !important;
}
/* Sidebar top logo area */
.sb-logo {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.2rem 0 0.1rem;
}
.sb-logo-icon {
    font-size: 1.1rem;
    color: #e8583a;
    font-family: 'Syne', sans-serif !important;
    font-weight: 800;
    line-height: 1;
}
.sb-logo-name {
    font-family: 'Syne', sans-serif !important;
    font-size: 1rem;
    font-weight: 700;
    color: #f0ede6;
    letter-spacing: -0.02em;
}
.sb-version {
    font-size: 0.58rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #383838;
    margin-top: 0.1rem;
    margin-bottom: 0.8rem;
}
/* Section headers */
.sb-section {
    font-size: 0.58rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #383838;
    padding-bottom: 0.35rem;
    border-bottom: 1px solid #1c1c20;
    margin-bottom: 0.7rem;
    margin-top: 1.1rem;
}
/* Sidebar controls */
[data-testid="stSlider"] label   { font-size: 0.75rem !important; color: #888 !important; }
/* Selected slider value */
[data-testid="stSlider"] [data-testid="stMarkdownContainer"] p {
    color: #e8583a !important;
    font-size: 0.78rem !important;
}
/* Slider track accent */
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
    background: #e8583a !important;
    border-color: #e8583a !important;
}
/* Legend dots */
.sb-legend { line-height: 2.1; font-size: 0.78rem; color: #888; }
.sb-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 0.5rem;
    vertical-align: middle;
}
/* Footer */
.sb-footer {
    font-size: 0.58rem;
    color: #2e2e2e;
    letter-spacing: 0.06em;
    margin-top: 0.5rem;
}

/* ══════════════════════════════════
   HEADER — centered
══════════════════════════════════ */
.eq-hero {
    text-align: center;
    padding: 2.5rem 0 0.5rem;
    margin-bottom: 0.5rem;
}
.eq-title {
    font-family: 'Syne', sans-serif;
    font-size: 3.4rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    color: #f0ede6;
    line-height: 1;
    margin: 0;
}
.eq-title-accent { color: #e8583a; }
.eq-subtitle {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    color: #444;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    margin-top: 0.9rem;
}

/* ══════════════════════════════════
   UPLOAD ZONE — centered dashed card
══════════════════════════════════ */
.upload-wrapper {
    max-width: 720px;
    margin: 1.5rem auto 0.5rem;
    border: 1.5px dashed #2e2e34;
    border-radius: 6px;
    padding: 2.2rem 2rem 1.8rem;
    background: transparent;
    transition: border-color 0.2s;
}
.upload-wrapper:hover { border-color: #e8583a66; }
[data-testid="stFileUploader"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
}
[data-testid="stFileUploaderDropzone"] {
    background: #18181c !important;
    border: 1px solid #242428 !important;
    border-radius: 4px !important;
}
.upload-hint {
    text-align: center;
    font-size: 0.78rem;
    color: #555;
    margin-top: 0.9rem;
    letter-spacing: 0.03em;
}
.upload-hint span { color: #e8583a; margin-right: 0.35rem; }

/* ══════════════════════════════════
   METRIC CARDS
══════════════════════════════════ */
.badge {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding: 0.25rem 0.7rem;
    border-radius: 2px;
}
.badge-dense  { background: #e8583a22; color: #e8583a; border: 1px solid #e8583a55; }
.badge-sparse { background: #4f9cf922; color: #4f9cf9; border: 1px solid #4f9cf955; }

/* ══════════════════════════════════
   TABS
══════════════════════════════════ */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 1px solid #1e1e22;
    gap: 0;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #444;
    padding: 0.75rem 1.5rem;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    transition: color 0.15s;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #e8583a !important;
    border-bottom-color: #e8583a !important;
}

/* ══════════════════════════════════
   BUTTONS
══════════════════════════════════ */
.stButton > button,
[data-testid="stDownloadButton"] > button {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.05em;
    background: #1a1a1e;
    color: #d0cec8;
    border: 1px solid #2a2a2e;
    border-radius: 3px;
    padding: 0.5rem 1.2rem;
    transition: all 0.15s;
}
.stButton > button:hover,
[data-testid="stDownloadButton"] > button:hover {
    background: #e8583a;
    border-color: #e8583a;
    color: #fff;
}

/* ══════════════════════════════════
   MISC
══════════════════════════════════ */
[data-testid="stAlert"] {
    background: #131316;
    border: 1px solid #222;
    border-radius: 4px;
    font-size: 0.78rem;
}
[data-testid="stDataFrame"] {
    border: 1px solid #222;
    border-radius: 4px;
    font-size: 0.78rem;
}
hr { border-color: #1e1e22; }
[data-testid="stSpinner"] { color: #e8583a; }
.conf-badge {
    display: inline-block;
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    padding: 0.12rem 0.45rem;
    border-radius: 2px;
    background: #e8583a1a;
    color: #e8583a;
    border: 1px solid #e8583a33;
    margin-left: 0.4rem;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _fig_bytes(fig, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi,
                bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _pil_to_png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def _render_detections(gray, text_boxes, eq_results, class1_threshold):
    fig, ax = plt.subplots(figsize=(12, 16))
    fig.patch.set_facecolor("#0d0d0f")
    ax.set_facecolor("#0d0d0f")
    ax.imshow(gray, cmap="gray", vmin=0, vmax=255)

    for x1, y1, x2, y2 in text_boxes:
        ax.add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=0.8, edgecolor="#4ade80",
            facecolor="#4ade80", alpha=0.06))

    for det in eq_results:
        x1, y1, x2, y2 = det["box"]
        cls, conf = det["class"], det["confidence"]
        if cls == 1 and conf < class1_threshold:
            continue
        color = "#e8583a" if cls == 0 else "#4f9cf9"
        ax.add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=2, edgecolor=color, facecolor=color, alpha=0.12))
        ax.add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=2, edgecolor=color, facecolor="none"))
        ax.text(x1+3, y1-4, f"{conf:.2f}",
                color=color, fontsize=6.5, fontweight="bold",
                fontfamily="monospace", verticalalignment="bottom")

    ax.axis("off")
    plt.tight_layout(pad=0)
    return fig


@st.cache_data(show_spinner=False)
def _render_diagnostic_cached(gray_key, gray_flat, binary_flat, blob_data,
                               font_size, text_boxes, eq_results,
                               img_width, img_height):
    gray   = [list(gray_flat  [r*img_width:(r+1)*img_width]) for r in range(img_height)]
    binary = [list(binary_flat[r*img_width:(r+1)*img_width]) for r in range(img_height)]

    blob_data  = [{"x1": t[0], "y1": t[1], "x2": t[2], "y2": t[3],
                   "height": t[4], "width": t[5], "area": t[6], "fill_ratio": t[7]}
                  for t in blob_data]
    eq_results = [{"box": t[0], "confidence": t[1], "class": t[2]}
                  for t in eq_results]

    BG = "#0d0d0f"
    PANEL = "#131316"

    fig, axes = plt.subplots(2, 3, figsize=(20, 13))
    fig.patch.set_facecolor(BG)
    fig.suptitle("pipeline diagnostic", fontsize=11,
                 fontfamily="monospace", y=1.01, color="#555")

    standalone = [d for d in eq_results if d["class"] == 0]
    inline     = [d for d in eq_results if d["class"] == 1]

    def _style(ax, title):
        ax.set_facecolor(PANEL)
        ax.set_title(title, fontsize=8, fontfamily="monospace", color="#666", pad=6)
        ax.axis("off")
        for spine in ax.spines.values():
            spine.set_edgecolor("#222")

    axes[0,0].imshow(gray,   cmap="gray", vmin=0, vmax=255)
    _style(axes[0,0], "01 · grayscale input")

    axes[0,1].imshow(binary, cmap="gray", vmin=0, vmax=1)
    _style(axes[0,1], "02 · binary (adaptive otsu)")

    heights = [b["height"] for b in blob_data]
    axes[0,2].set_facecolor(PANEL)
    axes[0,2].hist(heights, bins=55, color="#e8583a", edgecolor=BG, alpha=0.9)
    axes[0,2].axvline(font_size,        color="#f0ede6", lw=1.5,
                      label=f"font={font_size}px")
    axes[0,2].axvline(font_size * 1.9,  color="#4f9cf9", lw=1.2, ls="--",
                      label=f"tall={font_size*1.9:.0f}px")
    axes[0,2].axvline(font_size * 0.42, color="#a78bfa", lw=1.2, ls=":",
                      label=f"tiny={font_size*0.42:.0f}px")
    axes[0,2].legend(fontsize=7, facecolor=BG, edgecolor="#333",
                     labelcolor="#aaa")
    axes[0,2].set_xlabel("blob height (px)", fontsize=7, color="#555")
    axes[0,2].set_ylabel("count", fontsize=7, color="#555")
    axes[0,2].set_title("03 · blob height distribution", fontsize=8,
                         fontfamily="monospace", color="#666", pad=6)
    axes[0,2].tick_params(labelsize=6, colors="#444")
    for spine in axes[0,2].spines.values():
        spine.set_edgecolor("#222")

    axes[1,0].imshow(gray, cmap="gray", vmin=0, vmax=255, alpha=0.5)
    for b in blob_data:
        is_out = (b["height"] > font_size * 1.9 or
                  (b["width"] > font_size * 4 and b["height"] < font_size * 0.5))
        color = "#e8583a" if is_out else "#4ade80"
        axes[1,0].add_patch(patches.Rectangle(
            (b["x1"], b["y1"]), b["width"], b["height"],
            linewidth=1.0 if is_out else 0.4,
            edgecolor=color, facecolor="none",
            alpha=0.9 if is_out else 0.5))
    _style(axes[1,0], "04 · blob map  ·  green=normal  red=outlier")
    axes[1,0].set_visible(True)
    axes[1,0].axis("off")

    axes[1,1].imshow(gray, cmap="gray", vmin=0, vmax=255)
    for x1, y1, x2, y2 in text_boxes:
        axes[1,1].add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=1.2, edgecolor="#4ade80", facecolor="#4ade80", alpha=0.12))
    _style(axes[1,1], f"05 · text regions ({len(text_boxes)})")
    axes[1,1].axis("off")

    axes[1,2].imshow(gray, cmap="gray", vmin=0, vmax=255)
    for x1, y1, x2, y2 in text_boxes:
        axes[1,2].add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=0.8, edgecolor="#4ade80", facecolor="none"))
    for det in standalone:
        x1, y1, x2, y2 = det["box"]
        axes[1,2].add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=1.8, edgecolor="#e8583a", facecolor="#e8583a", alpha=0.15))
        axes[1,2].text(x1+2, y1-3, f"{det['confidence']:.2f}",
                       color="#e8583a", fontsize=5, fontweight="bold")
    for det in inline:
        x1, y1, x2, y2 = det["box"]
        axes[1,2].add_patch(patches.Rectangle(
            (x1, y1), x2-x1, y2-y1,
            linewidth=1.8, edgecolor="#4f9cf9", facecolor="#4f9cf9", alpha=0.15))
        axes[1,2].text(x1+2, y1-3, f"{det['confidence']:.2f}",
                       color="#4f9cf9", fontsize=5, fontweight="bold")
    _style(axes[1,2],
           f"06 · detections · red={len(standalone)} standalone · blue={len(inline)} inline")
    axes[1,2].axis("off")

    plt.tight_layout()
    return _fig_bytes(fig, dpi=120)


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
    # ── Logo ──
    st.markdown("""
    <div class="sb-logo">
      <span class="sb-logo-icon">∂</span>
      <span class="sb-logo-name">EqDetect</span>
    </div>
    <div class="sb-version">Equation Detector V2</div>
    """, unsafe_allow_html=True)

    st.markdown("<hr style='border-color:#1c1c20;margin:0 0 0.2rem'>", unsafe_allow_html=True)

    # ── Detection section ──
    st.markdown("<div class='sb-section'>Detection</div>", unsafe_allow_html=True)

    class1_threshold = st.slider(
        "Inline confidence threshold",
        min_value=0.0, max_value=1.0,
        value=0.25, step=0.05,
    )

    # ── Legend ──
    st.markdown("<hr style='border-color:#1c1c20;margin:1rem 0 0'>", unsafe_allow_html=True)
    st.markdown("<div class='sb-section'>Legend</div>", unsafe_allow_html=True)
    st.markdown("""
    <div class="sb-legend">
      <div><span class="sb-dot" style="background:#e8583a"></span>Standalone equation</div>
      <div><span class="sb-dot" style="background:#4f9cf9"></span>Inline equation</div>
      <div><span class="sb-dot" style="background:#4ade80"></span>Text region</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Footer ──
    st.markdown("<hr style='border-color:#1c1c20;margin:1rem 0 0.5rem'>", unsafe_allow_html=True)
    st.markdown(
        "<div class='sb-footer'>No OpenCV · No NumPy · Pure Python CCA</div>",
        unsafe_allow_html=True
    )


# ══════════════════════════════════════════════════════════════════════════════
# HEADER — centered
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div class="eq-hero">
  <div class="eq-title">Eq<span class="eq-title-accent">Detect</span></div>
  <div class="eq-subtitle">Mathematical Expression Localization &nbsp;·&nbsp; Connected Component Analysis</div>
</div>
""", unsafe_allow_html=True)

# ── Upload zone ────────────────────────────────────────────────────────────────
_l, _c, _r = st.columns([1, 3, 1])
with _c:
    uploaded = st.file_uploader(
        "Drop a document image — research paper, textbook, or assignment sheet",
        type=["png", "jpg", "jpeg"],
        label_visibility="visible"
    )

if uploaded is None:
    _l2, _c2, _r2 = st.columns([1, 3, 1])
    with _c2:
        st.markdown(
            "<div class='upload-hint'>"
            "<span>↑</span>Upload a document image to begin detection."
            "</div>",
            unsafe_allow_html=True
        )
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE
# ══════════════════════════════════════════════════════════════════════════════
run_cca_pipeline = _load_pipeline()
if run_cca_pipeline is None:
    st.error("Pipeline modules not found. Ensure the `pipeline/` folder is alongside `app.py`.")
    st.stop()

_cache_key = f"{uploaded.name}_{uploaded.size}"

if st.session_state.get("_cache_key") != _cache_key:
    suffix = os.path.splitext(uploaded.name)[1] or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(uploaded.getvalue())
        tmp_path = f.name

    with st.spinner("Running pipeline…"):
        try:
            gray, binary, blobs, font_size, text_boxes, eq_results = \
                run_cca_pipeline(tmp_path)
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

    has_inline = any(d["class"] == 1 for d in eq_results)
    doc_type   = "dense" if has_inline else "sparse"

    st.session_state["_cache_key"]  = _cache_key
    st.session_state["gray"]        = gray
    st.session_state["binary"]      = binary
    st.session_state["blobs"]       = blobs
    st.session_state["font_size"]   = font_size
    st.session_state["text_boxes"]  = text_boxes
    st.session_state["eq_results"]  = eq_results
    st.session_state["doc_type"]    = doc_type

gray       = st.session_state["gray"]
binary     = st.session_state["binary"]
blobs      = st.session_state["blobs"]
font_size  = st.session_state["font_size"]
text_boxes = st.session_state["text_boxes"]
eq_results = st.session_state["eq_results"]
doc_type   = st.session_state["doc_type"]


# ══════════════════════════════════════════════════════════════════════════════
# METRICS
# ══════════════════════════════════════════════════════════════════════════════
standalone_all  = [d for d in eq_results if d["class"] == 0]
inline_all      = [d for d in eq_results if d["class"] == 1]
inline_shown    = [d for d in inline_all if d["confidence"] >= class1_threshold]
total_shown     = len(standalone_all) + len(inline_shown)

badge_cls = "badge-dense" if doc_type == "dense" else "badge-sparse"
inline_value = f'{len(inline_shown)}<span style="font-size:1rem;color:#3a3a3a"> / {len(inline_all)}</span>'

st.markdown(f"""
<div style="display:flex; gap:0.75rem; flex-wrap:wrap; margin-bottom:0.5rem;">

  <div style="
      flex: 0 0 auto; width:180px;
      background:#131316; border:1px solid #222; border-radius:4px;
      border-top:2px solid #4ade80; padding:1.1rem 1.3rem;">
    <div style="font-family:'Syne',sans-serif;font-size:2.2rem;font-weight:800;
                color:#f0ede6;line-height:1;letter-spacing:-0.03em;">
      {total_shown}
    </div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;
                color:#555;text-transform:uppercase;letter-spacing:0.12em;
                margin-top:0.45rem;">
      Total detected
    </div>
  </div>

  <div style="
      flex: 0 0 auto; width:180px;
      background:#131316; border:1px solid #222; border-radius:4px;
      border-top:2px solid #e8583a; padding:1.1rem 1.3rem;">
    <div style="font-family:'Syne',sans-serif;font-size:2.2rem;font-weight:800;
                color:#f0ede6;line-height:1;letter-spacing:-0.03em;">
      {len(standalone_all)}
    </div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;
                color:#555;text-transform:uppercase;letter-spacing:0.12em;
                margin-top:0.45rem;">
      Standalone (class 0)
    </div>
  </div>

  <div style="
      flex: 0 0 auto; width:200px;
      background:#131316; border:1px solid #222; border-radius:4px;
      border-top:2px solid #4f9cf9; padding:1.1rem 1.3rem;">
    <div style="font-family:'Syne',sans-serif;font-size:2.2rem;font-weight:800;
                color:#f0ede6;line-height:1;letter-spacing:-0.03em;">
      {inline_value}
    </div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;
                color:#555;text-transform:uppercase;letter-spacing:0.12em;
                margin-top:0.45rem;">
      Inline shown / found
    </div>
  </div>

  <div style="
      flex: 0 0 auto; width:160px;
      background:#131316; border:1px solid #222; border-radius:4px;
      border-top:2px solid #a78bfa; padding:1.1rem 1.3rem;">
    <div style="font-family:'Syne',sans-serif;font-size:1.1rem;font-weight:800;
                color:#f0ede6;line-height:1;letter-spacing:-0.01em;
                margin-top:0.3rem;">
      <span class="badge {badge_cls}">{doc_type}</span>
    </div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;
                color:#555;text-transform:uppercase;letter-spacing:0.12em;
                margin-top:0.75rem;">
      Document type
    </div>
  </div>

</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs(["Detection", "Crops", "Diagnostic", "Data"])


# ── Tab 1: Detection overlay ──────────────────────────────────────────────────
with tab1:
    det_fig  = _render_detections(gray, text_boxes, eq_results, class1_threshold)
    det_data = _fig_bytes(det_fig, dpi=150)

    st.image(det_data, use_container_width=True)

    st.download_button(
        "⬇  Download annotated image",
        data=det_data,
        file_name=f"{os.path.splitext(uploaded.name)[0]}_detections.png",
        mime="image/png",
        use_container_width=True,
    )


# ── Tab 2: Equation Crops ─────────────────────────────────────────────────────
with tab2:
    try:
        from pipeline.crop_equations import crop_standalone
        _crop_module_ok = True
    except ImportError:
        _crop_module_ok = False

    standalone_dets = [d for d in eq_results if d["class"] == 0]

    if not standalone_dets:
        st.info("No standalone equations detected — nothing to crop.")
    elif not _crop_module_ok:
        st.error("crop_equations module not found. Add `pipeline/crop_equations.py`.")
    else:
        crops = crop_standalone(gray, eq_results, padding=10)

        st.markdown(
            f"<div style='font-size:0.7rem;color:#555;letter-spacing:0.1em;"
            f"text-transform:uppercase;margin-bottom:1.2rem'>"
            f"{len(crops)} standalone equation{'s' if len(crops)!=1 else ''} extracted"
            f"</div>",
            unsafe_allow_html=True
        )

        # ── Build ZIP in memory ────────────────────────────────────────────
        zip_buf = io.BytesIO()
        crop_pngs = []

        with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for c in crops:
                png_bytes = _pil_to_png_bytes(c["image"])
                fname     = f"eq_{c['index']:03d}_conf{c['confidence']:.2f}.png"
                crop_pngs.append((fname, png_bytes, c["confidence"]))
                zf.writestr(fname, png_bytes)

        zip_buf.seek(0)

        st.download_button(
            f"⬇  Download all {len(crops)} crops as ZIP",
            data=zip_buf.getvalue(),
            file_name=f"{os.path.splitext(uploaded.name)[0]}_crops.zip",
            mime="application/zip",
            use_container_width=True,
        )

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

        # ── Gallery: 3 columns ─────────────────────────────────────────────
        cols_per_row = 3
        rows_needed  = (len(crop_pngs) + cols_per_row - 1) // cols_per_row

        for row_i in range(rows_needed):
            cols = st.columns(cols_per_row)
            for col_i, col in enumerate(cols):
                idx = row_i * cols_per_row + col_i
                if idx >= len(crop_pngs):
                    break
                fname, png_bytes, conf = crop_pngs[idx]
                eq_num = idx + 1
                with col:
                    st.markdown(
                        f"<div style='font-size:0.6rem;color:#555;"
                        f"letter-spacing:0.1em;text-transform:uppercase;"
                        f"margin-bottom:0.3rem'>"
                        f"EQ·{eq_num:03d}"
                        f"<span class='conf-badge'>conf {conf:.2f}</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                    st.image(png_bytes, use_container_width=True)
                    st.download_button(
                        f"⬇ Save",
                        data=png_bytes,
                        file_name=fname,
                        mime="image/png",
                        key=f"crop_dl_{idx}",
                        use_container_width=True,
                    )
                    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)


# ── Tab 3: Diagnostic ─────────────────────────────────────────────────────────
with tab3:
    img_height = len(gray)
    img_width  = len(gray[0])

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
        img_width, img_height,
    )
    st.image(diag_data, use_container_width=True)

    st.download_button(
        "⬇  Download diagnostic image",
        data=diag_data,
        file_name=f"{os.path.splitext(uploaded.name)[0]}_diagnostic.png",
        mime="image/png",
        use_container_width=True,
    )


# ── Tab 4: Data table + histogram + CSV ───────────────────────────────────────
with tab4:
    rows = []
    for d in eq_results:
        x1, y1, x2, y2 = d["box"]
        cls, conf = d["class"], d["confidence"]
        if cls == 1 and conf < class1_threshold:
            continue
        rows.append({
            "x1":         x1, "y1": y1, "x2": x2, "y2": y2,
            "class":      cls,
            "type":       "standalone" if cls == 0 else "inline",
            "confidence": round(conf, 4),
            "width_px":   x2 - x1,
            "height_px":  y2 - y1,
        })

    if rows:
        try:
            import pandas as pd
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True)

            st.markdown(
                "<div style='font-size:0.7rem;color:#555;letter-spacing:0.1em;"
                "text-transform:uppercase;margin:1rem 0 0.5rem'>Confidence by class</div>",
                unsafe_allow_html=True
            )
            st.dataframe(
                df.groupby("type")["confidence"].describe().round(3),
                use_container_width=True,
            )
            csv_bytes = df.to_csv(index=False).encode()

        except ImportError:
            st.write(rows)
            import csv, io as _io
            buf = _io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
            csv_bytes = buf.getvalue().encode()

        st.download_button(
            "⬇  Download CSV",
            data=csv_bytes,
            file_name=f"{os.path.splitext(uploaded.name)[0]}_detections.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.markdown(
            "<div style='font-size:0.7rem;color:#555;letter-spacing:0.1em;"
            "text-transform:uppercase;margin:1.5rem 0 0.5rem'>Confidence distribution</div>",
            unsafe_allow_html=True
        )

        fig_conf, ax_conf = plt.subplots(figsize=(8, 2.8))
        fig_conf.patch.set_facecolor("#0d0d0f")
        ax_conf.set_facecolor("#131316")

        c0 = [d["confidence"] for d in eq_results if d["class"] == 0]
        c1 = [d["confidence"] for d in eq_results
              if d["class"] == 1 and d["confidence"] >= class1_threshold]

        if c0:
            ax_conf.hist(c0, bins=20, alpha=0.85, color="#e8583a",
                         label=f"Standalone ({len(c0)})", edgecolor="#0d0d0f")
        if c1:
            ax_conf.hist(c1, bins=20, alpha=0.85, color="#4f9cf9",
                         label=f"Inline ({len(c1)})", edgecolor="#0d0d0f")

        ax_conf.axvline(class1_threshold, color="#f0ede6", ls="--", lw=1,
                        label=f"Threshold ({class1_threshold:.2f})")
        ax_conf.legend(fontsize=7, facecolor="#131316",
                       edgecolor="#333", labelcolor="#aaa")
        ax_conf.set_xlabel("Confidence", fontsize=7, color="#555")
        ax_conf.set_ylabel("Count", fontsize=7, color="#555")
        ax_conf.tick_params(labelsize=6, colors="#444")
        for spine in ax_conf.spines.values():
            spine.set_edgecolor("#222")
        plt.tight_layout()
        st.pyplot(fig_conf)
        plt.close(fig_conf)

    else:
        st.info("No equations detected above the current threshold.")