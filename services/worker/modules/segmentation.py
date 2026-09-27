"""Comic text segmentation mask via ONNX Runtime (replaces the AGPL-3.0 `ultralytics` runtime dependency).

The model is ogkalu/comic-text-segmenter-yolov8m exported once to ONNX (scripts/export_segmenter.py, a dev-only
step that needs ultralytics). Post-processing reimplements YOLOv8-seg: confidence filter, NMS, mask = sigmoid(coef @
protos) cropped to its box, then letterbox padding removed and resized to the page.

SEGMENTER=none skips the model entirely and seeds the mask with the detector's text boxes (Apache-2.0 RT-DETR);
Otsu refinement in build_segmenter_mask then isolates the glyph strokes. Use it if the weights' licence is ruled out.
"""

import hashlib
import os
import threading
from pathlib import Path

import cv2
import numpy as np

from modules.utils.download import ModelDownloader  # noqa: F401  (ensures the models root exists)
from modules.utils.paths import get_user_data_dir

IMGSZ = 1024
DEFAULT_SHA256 = "688b01e8cefcff409efb8cd71e8df1e19328e186bf17825127536b71e9a31d88"
_session = None
_lock = threading.Lock()


def model_path() -> Path:
    return Path(os.environ.get("SEGMENTER_ONNX") or
                Path(get_user_data_dir()) / "models" / "segmentation" / "comic-text-segmenter.onnx")


def _load():
    global _session
    if _session is None:
        with _lock:
            if _session is None:
                import onnxruntime as ort

                path = model_path()
                if not path.exists():
                    raise RuntimeError(f"text segmenter model missing at {path} (see scripts/export_segmenter.py)")
                expected = os.environ.get("SEGMENTER_ONNX_SHA256", DEFAULT_SHA256)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if expected and digest != expected:
                    raise RuntimeError(f"text segmenter checksum mismatch: {digest}")
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] \
                    if os.environ.get("USE_GPU", "false").lower() == "true" else ["CPUExecutionProvider"]
                _session = ort.InferenceSession(str(path), providers=providers)
    return _session


def _letterbox(image: np.ndarray):
    h, w = image.shape[:2]
    r = min(IMGSZ / h, IMGSZ / w)
    nh, nw = round(h * r), round(w * r)
    top, left = (IMGSZ - nh) // 2, (IMGSZ - nw) // 2
    canvas = np.full((IMGSZ, IMGSZ, 3), 114, np.uint8)
    canvas[top:top + nh, left:left + nw] = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)
    return canvas, (top, left, nh, nw)


def segment(image: np.ndarray, conf: float = 0.25, iou: float = 0.7) -> np.ndarray:
    """RGB page → uint8 mask (0/255) of text pixels."""
    h, w = image.shape[:2]
    canvas, (top, left, nh, nw) = _letterbox(image)
    x = canvas.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    out, protos = _load().run(None, {"images": x})
    preds = out[0].T  # (anchors, 4 box + 1 class + 32 coefs)
    preds = preds[preds[:, 4] > conf]
    mask = np.zeros((h, w), np.uint8)
    if not len(preds):
        return mask
    cx, cy, bw, bh = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
    boxes = np.stack([cx - bw / 2, cy - bh / 2, bw, bh], 1)
    keep = cv2.dnn.NMSBoxes(boxes.tolist(), preds[:, 4].tolist(), conf, iou)
    keep = np.array(keep).reshape(-1)
    if not len(keep):
        return mask
    preds, boxes = preds[keep], boxes[keep]
    c, ph, pw = protos.shape[1:]
    m = 1 / (1 + np.exp(-(preds[:, 5:] @ protos[0].reshape(c, -1)))).reshape(-1, ph, pw)
    scale = ph / IMGSZ
    full = np.zeros((IMGSZ, IMGSZ), np.uint8)
    rows, cols = np.arange(ph)[:, None], np.arange(pw)[None, :]
    for mi, (x1, y1, bw_, bh_) in zip(m, boxes, strict=True):
        inside = (rows >= y1 * scale) & (rows < (y1 + bh_) * scale) & (cols >= x1 * scale) & (cols < (x1 + bw_) * scale)
        crop = np.where(inside, mi, 0).astype(np.float32)
        up = cv2.resize(crop, (IMGSZ, IMGSZ), interpolation=cv2.INTER_LINEAR)
        full[up > 0.5] = 255
    full = full[top:top + nh, left:left + nw]
    return cv2.resize(full, (w, h), interpolation=cv2.INTER_NEAREST)


def boxes_mask(image: np.ndarray, blocks) -> np.ndarray:
    """Model-free seed: fill the detector's text boxes."""
    h, w = image.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    for b in blocks or []:
        x1, y1, x2, y2 = [int(v) for v in b.xyxy]
        mask[max(0, y1):min(h, y2), max(0, x1):min(w, x2)] = 255
    return mask


def text_mask(image: np.ndarray, blocks, conf: float) -> np.ndarray:
    if os.environ.get("SEGMENTER", "onnx").lower() == "none":
        return boxes_mask(image, blocks)
    return segment(image, conf)
