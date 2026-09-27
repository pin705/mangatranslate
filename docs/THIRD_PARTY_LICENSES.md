# Third-party code and licences

Audited 2026-09-27 against the installed package metadata and the upstream repositories. Model weights, fonts and AI
APIs are covered in [MODEL_LICENSES.md](MODEL_LICENSES.md). This is an engineering audit, not legal advice. Have
counsel confirm before launch, especially the items marked **review**.

## Vendored source

| Component | Where | Licence | Obligations / notes |
|---|---|---|---|
| luxivint/ai-manga-translator @ `74a85b0` | `services/worker/` (modules/, app/, imkit/, scripts/) | Apache-2.0 | Keep `LICENSE` + `NOTICE`, state changes (git history). Built for an English→Turkish reading site: its scanlation-ad removal and brand-stamp features are **disabled by default and unused by the production pipeline**. The stamp asset and the author's queue worker were removed. The remaining ad code in `scripts/local_batch.py` (dev CLI) is scheduled for deletion. |
| ogkalu2/comic-translate @ `8977b91` | upstream of the above | Apache-2.0 | Same obligations. Source for future local OCR engines (manga-ocr, PP-OCR). |
| lumina-tl/lumina | reference only, no code copied | MIT | — |
| wesleytaetae/comtexia | not used | none (all rights reserved) | Repo contains no code or licence. Do not copy. |
| zyddnys/manga-image-translator, dmMaze/BallonsTranslator | not used | GPL-3.0 | Deliberately avoided to keep on-prem/desktop distribution possible. |

## Runtime dependencies

### API (`services/api`)
| Package | Licence |
|---|---|
| fastapi, sqlalchemy, alembic, pydantic, pydantic-settings, argon2-cffi | MIT |
| uvicorn, httpx | BSD-3-Clause |
| boto3 | Apache-2.0 |
| email-validator | Unlicense |
| psycopg / psycopg-binary 3 | LGPL-3.0: used unmodified as a dynamically loaded library. No obligations for a hosted service. If you distribute images, keep the library replaceable (it is a normal wheel). |

### Worker (`services/worker`)
| Package | Licence | Notes |
|---|---|---|
| onnxruntime (or onnxruntime-gpu) | MIT | |
| opencv-python-headless | Apache-2.0 | |
| numpy, shapely, uvicorn | BSD | |
| pillow | MIT-CMU (HPND) | |
| PySide6 / shiboken6 (Qt 6) | LGPL-3.0 (chosen option of LGPL/GPL) | Offscreen text rendering. Used unmodified via wheels. Fine for SaaS. **Review** if you ever ship the worker to customers: LGPL relinking terms apply. |
| requests, msgpack, pythainlp, janome | Apache-2.0 | |
| mahotas, jieba, jaconv, pyclipper, six, keyring, pdfplumber | MIT | |
| photoshopapi, send2trash | BSD-3-Clause | |
| rarfile | ISC | |
| wget | Public domain | |
| py7zr | LGPL-2.1+ | Unused by the service pipeline. Candidate for removal. |
| img2pdf | LGPL-3.0 | Unused by the service pipeline. Candidate for removal. |
| psycopg2-binary | LGPL with exceptions | Only the vendored CLI's optional usage logging uses it. Candidate for removal. |

### Removed on purpose
| Package | Licence | Why |
|---|---|---|
| ultralytics | **AGPL-3.0** | Network use would oblige us to publish our service source (or buy an Ultralytics licence). The text segmenter now runs as ONNX through onnxruntime (`modules/segmentation.py`). `ultralytics` is only used offline, once, by `scripts/export_segmenter.py`. |
| torch / torchvision | BSD | No longer needed at runtime (≈1 GB smaller image). |

### Web (`apps/web`)
See `apps/web/package.json`: Next.js (MIT), React (MIT), Tailwind CSS (MIT), shadcn/ui components (MIT, copied into the repo), Radix UI (MIT), lucide-react (ISC), next-intl (MIT). Run `pnpm licenses list` for the full tree.

## Fonts and art
| Asset | Licence |
|---|---|
| `services/worker/assets/fonts/Mali-Medium.ttf` | SIL Open Font License 1.1 (`Mali-OFL.txt` alongside). Commercial use and embedding in images are allowed. The font may not be sold on its own. |
| ~~`Comic Geek.ttf`~~ (removed) | "All rights reserved", no licence. It also lacked every Vietnamese diacritic glyph. |
| Pepper&Carrot pages (tests, landing showcase) | CC-BY 4.0, David Revoy. Credit shown wherever displayed. |

## Services / APIs
| Service | Terms to respect |
|---|---|
| OpenAI-compatible translation provider (OpenAI, DeepSeek, Gemini, gateways) | Each provider's API terms and data-use policy. Disclose in the Privacy Policy that page text is sent to the translation provider. |
| Qwen-VL via DashScope (Alibaba Cloud) for OCR | Page images are sent to Alibaba Cloud. Disclose it, and **review** data-residency expectations for your market. |
| payOS | Merchant terms, and prohibited goods list (**review** copyright positioning). |
| Cloudflare R2 | Standard terms. |
