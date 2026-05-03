# Equation Detector

A from-scratch mathematical equation localization system for document images — no OpenCV, no NumPy. Built entirely on connected component analysis (CCA), Edge Detection ,blob statistics, and multi-pass scoring.

---

## What it does

Given a document image (research paper, textbook, assignment sheet, lecture slide), the pipeline:

1. Binarizes the image using Otsu thresholding
2. Finds every ink blob via connected component analysis
3. Estimates font size from the modal blob height
4. Detects document type (dense vs sparse)
5. Groups blobs into candidate regions
6. Classifies standalone equations (Pass 1)
7. Scans text regions for inline equations (Pass 2, dense docs only)
8. Outputs annotated images + a CSV of bounding boxes with confidence scores

**Class 0** = standalone/display equation (red boxes)  
**Class 1** = inline equation within a text line (blue boxes)

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Usage

### Streamlit app
```bash
streamlit run app.py
```

### Command line (Windows)
```bash
run.bat path\to\image.png results\
```

### Python API
```python
from pipeline.pipeline import run_cca_pipeline

gray, binary, blobs, font_size, text_boxes, eq_results = run_cca_pipeline(
    "paper.png", debug=False
)

```


## CSV format

| Column | Type | Description |
|--------|------|-------------|
| x1 | int | Left edge of bounding box |
| y1 | int | Top edge of bounding box |
| x2 | int | Right edge of bounding box |
| y2 | int | Bottom edge of bounding box |
| class | int | 0 = standalone, 1 = inline |
| confidence | float | Score normalized to [0, 1] |

---

## How it works

### Document type detection
The pipeline classifies documents as **dense** (research papers, textbooks) or **sparse** (assignment sheets, slides) based on ink density, body blob ratio, and blobs-per-line. Only dense documents run Pass 2.

### Pass 1 — Standalone equations
Regions are scored on: blob height variance (`cv_h`), aspect ratio variance (`cv_ar`), outlier blob ratio (fraction bars, tall symbols), region height relative to font size, and center span. Hard guards reject single-line text, headings, and uniform paragraphs.

### Pass 2 — Inline equations (dense docs only)
Each text region is split into lines, then lines into word-level clusters. Each cluster is scored for: fraction bars, tall symbols (height > 1.8× font), tiny blobs (height < 0.4× font, i.e. superscripts), and height variance. A cluster fires as an inline equation only if it scores significantly above the baseline of its neighbouring clusters on the same line — this prevents normal text from accumulating soft scores.

### No external CV libraries
All image processing is implemented from scratch in pure Python: Gaussian blur, Sobel edges, Otsu binarization, BFS flood fill, and Union-Find region grouping.

---

## Tuning

| Parameter | Location | Effect |
|-----------|----------|--------|
| `confidence <= 0.3` | `standalone_equations.py` | Min confidence for standalone detection |
| `score >= 3.5` | `inline_equations.py` | Min score for inline cluster |
| `score_delta >= 4.0` | `inline_equations.py` | How anomalous vs line baseline |
| `baseline < 1.0` | `inline_equations.py` | Rest of line must look like text |
| `len > 20` | `inline_equations.py` | Max blobs per cluster (kills full lines) |
| `class1_threshold` | `app.py` / `plot_csv.py` | Post-hoc inline filtering via CSV |

---

## Limitations

- Handwritten documents: not supported (blob size distribution is too irregular for font-size estimation)
- Very low resolution scans (< 100 DPI): Otsu binarization degrades
- Colored backgrounds: grayscale conversion may lose contrast
- 2-column layouts: grouping sometimes merges across columns; reduce `h_gap_factor`

---

## No dependencies on

- OpenCV
- NumPy
- scikit-image
- Any ML model or pretrained weights