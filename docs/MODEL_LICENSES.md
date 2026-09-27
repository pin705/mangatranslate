# Models

Every model runs through ONNX Runtime and is downloaded and checksum-verified **at image build time**
(`services/worker/scripts/fetch_models.py`). Workers load each model once per process and reuse it.

| Stage | Model | Source | Version / pin | SHA-256 | Licence (as published) | Runtime | Commercial notes |
|---|---|---|---|---|---|---|---|
| Text/bubble detection | RT-DETR v4-s int8 | `huggingface.co/ogkalu/comic-text-and-bubble-detector` (`detector-v4-s_int8.onnx`) | checksum-pinned | `5fe9e4f5…c931ea79` | Apache-2.0 (model card) | CPU ~1–2.5 s/page (M1) | Training data provenance is not documented. **Review**. |
| Font colour/direction | YuzuMarker font detector | `huggingface.co/ogkalu/yuzumarker-font-detection-onnx` | checksum-pinned | `99dd351e…836f75d4f` | MIT | CPU, fast | — |
| Text segmentation | comic-text-segmenter YOLOv8m, exported to ONNX (imgsz 1024, opset 17) | `huggingface.co/ogkalu/comic-text-segmenter-yolov8m` → `scripts/export_segmenter.py` | our export | `688b01e8…e9a31d88` | Apache-2.0 on the model card | CPU ~0.9 s/page | **Review**: Ultralytics states that models trained with its framework fall under AGPL-3.0 unless licensed. We removed the AGPL *code*. Whether the *weights* carry obligations is a legal question. If counsel advises against using the weights, set `SEGMENTER=none`: the mask is then built from the Apache-2.0 detector's boxes plus Otsu thresholding (tested in CI). |
| Inpainting (clean mode) | LaMa, manga fine-tune | `huggingface.co/ogkalu/lama-manga-onnx-dynamic` | checksum-pinned | `de31ffa5…bb095315f9` | Apache-2.0 (LaMa: Apache-2.0) | CPU ~3–13 s/page | Fine-tune dataset provenance is not documented. **Review**. |
| Inpainting (overlay mode) | OpenCV Telea | OpenCV | — | — | Apache-2.0 | CPU, fast | — |
| OCR | Qwen3-VL-Flash (vision LLM) | DashScope API (`OCR_BASE_URL`) | provider-managed | — | API terms | remote | Images leave our infrastructure. Replaceable by any OpenAI-compatible vision model via `/admin/providers`. |
| Translation | gpt-5.4-mini (default) + optional fallback | any OpenAI-compatible API | provider-managed | — | API terms | remote | Text leaves our infrastructure. |

The full SHA-256 values are in `modules/utils/download.py` (Hugging Face models) and `modules/segmentation.py`
(segmenter).

## Hardware

| | CPU worker (default) | GPU worker (optional) |
|---|---|---|
| Image | `infra/docker/worker.Dockerfile` | same, `--build-arg ORT_PACKAGE="onnxruntime-gpu[cuda,cudnn]==1.24.4"` |
| Python | 3.12 | 3.12 |
| Runtime | onnxruntime (CPU) | onnxruntime-gpu with pip-bundled CUDA 12 / cuDNN 9. The host needs only the NVIDIA driver and container toolkit. |
| PyTorch | not used | not used |
| Memory | ~2.5 GB RAM per worker process (LaMa dominates) | ~3 GB VRAM for LaMa plus the segmenter at 1024 px |
| Throughput measured | detect + clean ≈ 5–15 s/page on Apple M1 CPU (18 test pages) | not measured yet |

Startup fails clearly (`PRELOAD_MODELS=true`, the default) if Qt, the font or a model file is missing or has a
wrong checksum.

## Not used (and why)

- **manga-ocr / PP-OCRv5 / pororo** (local OCR, Apache-2.0): their download URLs remain in the vendored registry
  but no engine is wired in. They are candidates to replace the paid vision OCR once quality has been measured.
- **Manga109-trained models**: Manga109 is for non-commercial research only.
