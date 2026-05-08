from pipeline.blob_analysis import run_blob_analysis
from pipeline.preprocessing import preprocess

pre = preprocess("test8.2.jpeg")
blob_res = run_blob_analysis(pre["binary"])
blobs = blob_res["blobs"]
font_size = blob_res["font_size"]
width, height = pre["width"], pre["height"]

total_ink = sum(b["area"] for b in blobs)
ink_density = total_ink / (width * height)
body_blobs = sum(1 for b in blobs if font_size * 0.6 <= b["height"] <= font_size * 1.4)
body_ratio = body_blobs / len(blobs)
est_lines = height / (font_size * 1.5)
blobs_per_line = len(blobs) / est_lines

print(f"font_size      = {font_size}")
print(f"ink_density    = {ink_density:.4f}  (need > 0.04)")
print(f"body_ratio     = {body_ratio:.4f}  (need >= 0.60)")
print(f"blobs_per_line = {blobs_per_line:.1f}   (need > 20)")
print(f"total_blobs    = {len(blobs)}")