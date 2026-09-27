"""Adapter between the job system and the vendored engine (modules/ + scripts/local_batch.py).

Stages are pure functions over numpy images and JSON-serialisable regions so each can run as its own task,
on any worker, and be re-run alone (the editor re-typesets from stored regions + the cleaned image).
Models are loaded once per process (engine factories and local_batch keep module-level caches).
"""

import copy
import io
import os
import sys
from argparse import Namespace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

_state: dict = {}


def init() -> None:
    """Create the offscreen Qt app, register the font and warm the models. Idempotent."""
    if _state:
        return
    argv, sys.argv = sys.argv, [sys.argv[0]]
    try:
        from PySide6 import QtWidgets

        import scripts.local_batch as lb

        args = lb.parse_args()
    finally:
        sys.argv = argv
    _state["app"] = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    args.font_file = os.environ.get("FONT_FILE", "assets/fonts/Mali-Medium.ttf")
    args.resolved_font = lb.resolve_font(args)
    args.gpu = os.environ.get("USE_GPU", "false").lower() == "true"
    _state.update(lb=lb, args=args)


def _args(source_lang: str, target_lang: str) -> Namespace:
    args = copy.copy(_state["args"])
    args.source_lang, args.target_lang = source_lang, target_lang
    return args


def decode(data: bytes) -> np.ndarray:
    """Bytes → RGB array (the engine's convention, see imkit.read_image)."""
    img = Image.open(io.BytesIO(data))
    return np.array(img.convert("RGB"))


def encode_png(img: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def encode_jpg(img: np.ndarray, quality: int = 92) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(img).convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


# --- regions <-> engine blocks --------------------------------------------------------

def _hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*[int(c) for c in rgb[:3]]) if rgb and len(rgb) >= 3 else "#000000"


def _box(v) -> list[int] | None:
    return [int(round(float(x))) for x in v] if v is not None and len(v) == 4 else None


def blocks_to_regions(blocks, render_boxes) -> list[dict]:
    regions = []
    for i, (b, render) in enumerate(zip(blocks, render_boxes, strict=True)):
        regions.append({
            "id": f"r{i}",
            "bbox": render,
            "text": b.text or "",
            "translation": b.translation or "",
            "confidence": None,  # the vision OCR returns no per-crop confidence
            "style": {"font_size": None, "alignment": "center", "color": _hex(b.font_color), "outline": True,
                      "uppercase": False},
            "engine": {"text_xyxy": _box(b.xyxy), "bubble_xyxy": _box(b.bubble_xyxy), "text_class": b.text_class,
                       "direction": b.direction, "font_color": list(b.font_color or ()), "angle": float(b.angle or 0),
                       "source_lang": b.source_lang},
        })
    return regions


def regions_to_blocks(regions: list[dict], use_render_box: bool):
    from modules.utils.textblock import TextBlock

    blocks = []
    for r in regions:
        e = r.get("engine") or {}
        box = r["bbox"] if use_render_box or not e.get("text_xyxy") else e["text_xyxy"]
        b = TextBlock(text_bbox=np.array(box, dtype=np.int32),
                      bubble_bbox=np.array(e["bubble_xyxy"]) if e.get("bubble_xyxy") else None,
                      text_class=e.get("text_class", "text_free"), direction=e.get("direction", ""),
                      font_color=tuple(e.get("font_color") or ()), angle=e.get("angle", 0),
                      text=r.get("text", ""), translation=r.get("translation", ""),
                      source_lang=e.get("source_lang", ""))
        blocks.append(b)
    return blocks


# --- stages ----------------------------------------------------------------------------

def detect(image: np.ndarray, source_lang: str, target_lang: str):
    """Find text blocks (bubbles and free text). OCR fills block.text afterwards (see ai.ocr)."""
    init()
    from modules.utils.language_utils import language_codes

    blocks = _state["lb"].TextBlockDetector(_state["lb"].LocalSettings(_args(source_lang, target_lang))).detect(image)
    code = language_codes.get(source_lang, "en")
    for b in blocks:
        b.source_lang = code
    return blocks


def filter_ocr(blocks, image: np.ndarray, source_lang: str):
    """Drop empty/duplicate detections and order blocks in reading order."""
    lb = _state["lb"]
    from modules.utils.textblock import sort_blk_list

    blocks = lb.drop_non_english_ocr_blocks(blocks, source_lang)
    blocks = lb.prune_ocr_blocks(blocks, image)
    return sort_blk_list(blocks, right_to_left=source_lang == "Japanese")


def clean(image: np.ndarray, blocks, mode: str) -> np.ndarray:
    """Remove source text. clean = segmentation mask + LaMa inpainting; overlay = same mask, fast OpenCV fill."""
    init()
    lb = _state["lb"]
    if not blocks:
        return image.copy()
    mask = lb.build_segmenter_mask(image, blocks)
    if mask.sum() == 0:
        return image.copy()
    if mode == "overlay":
        return cv2.inpaint(image, (mask > 0).astype(np.uint8) * 255, 5, cv2.INPAINT_TELEA)
    return lb.block_inpaint(image, mask, lb.Config(hd_strategy="Resize", hd_strategy_resize_limit=2048))


def render_boxes(image: np.ndarray, cleaned: np.ndarray, blocks) -> list[list[int]]:
    """Where translated text should go (bubble interior for bubbles). Computed once; the editor may move it."""
    init()
    from modules.rendering.render import get_best_render_area

    work = [b.deep_copy() for b in blocks]
    get_best_render_area(work, image, cleaned)
    return [_box(b.xyxy) for b in work]


def render(original: np.ndarray, cleaned: np.ndarray, regions: list[dict], source_lang: str,
           target_lang: str) -> tuple[np.ndarray, list[str]]:
    """Typeset translations onto the cleaned page. Returns (image, ids of regions whose text overflowed)."""
    init()
    lb, args = _state["lb"], _args(source_lang, target_lang)
    from PySide6 import QtCore
    from PySide6.QtGui import QColor

    from app.ui.canvas.save_renderer import ImageSaveRenderer
    from app.ui.canvas.text.text_item_properties import TextItemProperties
    from app.ui.canvas.text_item import OutlineInfo, OutlineType
    from modules.rendering.render import is_vertical_block, pyside_word_wrap
    from modules.utils.image_utils import get_smart_text_color
    from modules.utils.language_utils import get_language_code, get_layout_direction, is_no_space_lang
    from modules.utils.translator_utils import format_translations

    target_code = get_language_code(target_lang)
    # Untranslated source regions (SFX, noise) get their original pixels back instead of a blank patch.
    text_blocks = regions_to_blocks(regions, use_render_box=False)
    lb.suppress_noisy_ocr_blocks(text_blocks, source_lang)
    cleaned = lb.restore_untranslated_regions(original, cleaned, text_blocks)

    blocks = regions_to_blocks(regions, use_render_box=True)
    for b, t in zip(blocks, text_blocks, strict=True):
        b.translation = t.translation
    cleaned = lb.clear_light_free_text_render_regions(cleaned, blocks)
    cleaned = lb.clear_light_bubble_text_render_regions(cleaned, blocks, original)

    align = {"left": QtCore.Qt.AlignmentFlag.AlignLeft, "center": QtCore.Qt.AlignmentFlag.AlignCenter,
             "right": QtCore.Qt.AlignmentFlag.AlignRight}
    direction = get_layout_direction(target_lang)
    items, overflow = [], []
    for r, b in zip(regions, blocks, strict=True):
        style = r.get("style") or {}
        format_translations([b], target_code, upper_case=bool(style.get("uppercase")))
        text = b.translation
        if not text or len(text) == 1:
            continue
        x1, y1, w, h = [int(v) for v in b.xywh]
        vertical = is_vertical_block(b, target_code)
        outline_width = 2.0 if style.get("outline", True) else 0.0
        fixed = style.get("font_size")
        max_size, min_size = (fixed, fixed) if fixed else (args.max_font_size, args.min_font_size)
        wrapped, size, rw, rh = pyside_word_wrap(
            text, args.resolved_font, w, h, 1.0, outline_width, False, False, False, align[style.get("alignment",
            "center")], direction, max_size, min_size, vertical, return_metrics=True)
        if rh > h * 1.05 or rw > w * 1.05:
            overflow.append(r["id"])
        if is_no_space_lang(target_code):
            wrapped = wrapped.replace(" ", "")
        color = QColor(style["color"]) if style.get("color") else get_smart_text_color(b.font_color, QColor("#000000"))
        outline = lb.contrast_outline_color(color) if style.get("outline", True) else None
        props = TextItemProperties(
            text=wrapped, font_family=args.resolved_font, font_size=size, text_color=color,
            alignment=align[style.get("alignment", "center")], line_spacing=1.0, outline_color=outline,
            outline_width=outline_width, bold=False, italic=False, underline=False,
            position=(int(x1 + max(0, (w - rw) / 2)), int(y1 + max(0, (h - rh) / 2))), rotation=b.angle, scale=1.0,
            transform_origin=b.tr_origin_point, width=rw, height=rh, direction=direction, vertical=vertical,
            selection_outlines=[OutlineInfo(0, len(wrapped), outline, outline_width, OutlineType.Full_Document)]
            if outline else [],
        )
        items.append(props.to_dict())

    renderer = ImageSaveRenderer(cleaned)
    renderer.add_state_to_image({"text_items_state": items})
    return renderer.render_to_image(), overflow
