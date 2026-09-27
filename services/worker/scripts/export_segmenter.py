"""Dev-only, run once: export ogkalu/comic-text-segmenter-yolov8m to ONNX for modules/segmentation.py.

Needs `pip install ultralytics onnx` in a throwaway environment. ultralytics is AGPL-3.0, which is why it is not a
runtime dependency of the worker; see docs/MODEL_LICENSES.md for the open question about the weights themselves.
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.segmentation import IMGSZ, model_path  # noqa: E402
from modules.utils.download import ModelDownloader, ModelID  # noqa: E402

from ultralytics import YOLO  # noqa: E402

ModelDownloader.get(ModelID.COMIC_TEXT_SEGMENTER)
pt = ModelDownloader.primary_path(ModelID.COMIC_TEXT_SEGMENTER)
out = Path(YOLO(str(pt)).export(format="onnx", imgsz=IMGSZ, dynamic=False, simplify=False, opset=17))
model_path().parent.mkdir(parents=True, exist_ok=True)
out.replace(model_path())
print(model_path(), hashlib.sha256(model_path().read_bytes()).hexdigest())
