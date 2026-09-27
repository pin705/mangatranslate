# Build from the repo root:
#   CPU: docker build -f infra/docker/worker.Dockerfile --build-arg SEGMENTER_ONNX_URL=https://… -t mangatranslate-worker .
#   GPU: add --build-arg ORT_PACKAGE="onnxruntime-gpu[cuda,cudnn]==1.24.4" and run with --gpus all, USE_GPU=true
FROM python:3.12-slim
ARG ORT_PACKAGE=onnxruntime
ARG SEGMENTER_ONNX_URL=""
# "none" = model-free text mask (detector boxes + Otsu), for local builds without the exported segmenter
ARG SEGMENTER=onnx
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    QT_QPA_PLATFORM=offscreen XDG_DATA_HOME=/models API_PATH=/srv/api HOME=/srv SEGMENTER=$SEGMENTER
# Qt offscreen rendering needs these system libraries (no display server).
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libegl1 libglib2.0-0 libfontconfig1 libfreetype6 libxkbcommon0 libdbus-1-3 \
      libx11-6 libx11-xcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
      libxcb-render-util0 libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0 libxext6 libxrender1 libsm6 libice6 \
      fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --home /srv app && mkdir -p /models && chown app /models
WORKDIR /srv/worker
COPY services/worker/requirements.txt services/api/pyproject.toml /tmp/
RUN pip install uv \
 && grep -v '^onnxruntime' /tmp/requirements.txt > /tmp/req.txt \
 && uv pip install --system -r /tmp/req.txt "$ORT_PACKAGE" \
 && uv pip install --system -r /tmp/pyproject.toml
COPY services/api/mtapi /srv/api/mtapi
COPY services/worker/ ./
USER app
# Models are downloaded and checksum-verified at build time, never per job.
RUN SEGMENTER_ONNX_URL="$SEGMENTER_ONNX_URL" python scripts/fetch_models.py
HEALTHCHECK --interval=60s --timeout=10s CMD python -c "import os,sys,time; sys.exit(time.time() - os.path.getmtime('/tmp/worker-alive') > 180)"
CMD ["python", "runner.py"]
