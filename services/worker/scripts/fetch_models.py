"""Download and checksum-verify every model the worker needs. Run at image build time so jobs never download.

The text segmenter ONNX is not on Hugging Face (we export it ourselves, see export_segmenter.py): host it in your
own bucket and pass SEGMENTER_ONNX_URL. Checksums are pinned in modules/utils/download.py and modules/segmentation.py.
"""
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.segmentation import DEFAULT_SHA256, model_path  # noqa: E402
from modules.utils.download import ModelDownloader, ModelID  # noqa: E402

for model in (ModelID.RTDETR_V4S_INT8_ONNX, ModelID.LAMA_ONNX, ModelID.FONT_DETECTOR_ONNX):
    ModelDownloader.get(model)
    print("ok", model.value)

seg = model_path()
if os.environ.get("SEGMENTER", "onnx") != "none" and not seg.exists():
    url = os.environ.get("SEGMENTER_ONNX_URL")
    if not url:
        sys.exit(f"text segmenter missing at {seg}; set SEGMENTER_ONNX_URL or SEGMENTER=none")
    seg.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, seg)  # noqa: S310 — operator-provided https URL
if seg.exists():
    digest = hashlib.sha256(seg.read_bytes()).hexdigest()
    if digest != os.environ.get("SEGMENTER_ONNX_SHA256", DEFAULT_SHA256):
        sys.exit(f"text segmenter checksum mismatch: {digest}")
    print("ok segmenter", digest)
