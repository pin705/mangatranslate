#!/usr/bin/env bash
# Go/no-go run: full pipeline (OCR + translate) on samples/<code>/input -> samples/<code>/output.
# Uses OPENAI_API_KEY / OPENAI_BASE_URL for both OCR (vision) and translation.
# Usage: scripts/try_samples.sh [cn:Chinese kr:Korean ja:Japanese]   (TARGET_LANG=English to switch)
set -euo pipefail
cd "$(dirname "$0")/.."
SAMPLES=../../samples
MODEL=${OPENAI_MODEL:-gpt-5.4-mini}
for pair in "${@:-cn:Chinese kr:Korean ja:Japanese}"; do
  for item in $pair; do
    code=${item%%:*}; lang=${item#*:}
    echo "=== $lang -> ${TARGET_LANG:-Vietnamese} ($code)"
    start=$(date +%s)
    OCR_BASE_URL=${OCR_BASE_URL:-${OPENAI_BASE_URL:-https://api.openai.com/v1}} \
    OCR_API_KEY=${OCR_API_KEY:-$OPENAI_API_KEY} OCR_MODEL=${OCR_MODEL:-$MODEL} OPENAI_MODEL=$MODEL \
    BATCH_PIPELINE=true \
    QWEN_GRID_OCR_USAGE_PATH=$SAMPLES/$code/ocr_usage.json \
    BATCH_TRANSLATE_USAGE_PATH=$SAMPLES/$code/translate_usage.jsonl \
      .venv/bin/python scripts/local_batch.py \
        --input "$SAMPLES/$code/input" --output "$SAMPLES/$code/output" \
        --source-lang "$lang" --target-lang "${TARGET_LANG:-Vietnamese}" \
        --ocr "Qwen3-VL-Flash Grid OCR" --font-file assets/fonts/Mali-Medium.ttf --output-format jpg
    echo "=== $code done in $(( $(date +%s) - start ))s"
  done
done
