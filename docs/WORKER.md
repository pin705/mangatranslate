# Worker

`python runner.py` (image `infra/docker/worker.Dockerfile`). See ARCHITECTURE.md for the pipeline and queue design.

## Configuration

| Env | Default | Meaning |
|---|---|---|
| `WORKER_QUEUES` | `default` | Comma list: `default` (everything) and/or `gpu` |
| `MODEL_QUEUE` (API + workers) | `default` | Queue for `page.prepare` / `page.reinpaint`. Set to `gpu` to send model-heavy work to GPU workers. |
| `USE_GPU` | `false` | Use CUDA in onnxruntime (needs the GPU image) |
| `PRELOAD_MODELS` | `true` | Load Qt, font and models at startup and fail fast if anything is missing |
| `SEGMENTER` | `onnx` | `none` = model-free text mask (see MODEL_LICENSES.md) |
| `WORKER_POLL_SECONDS` | `1.5` | Idle poll interval |
| `FONT_FILE` | `assets/fonts/Mali-Medium.ttf` | Render font (must cover Vietnamese) |
| Provider seeds | see `.env.example` | Used once to fill `providers`. Afterwards, edit in `/admin/providers` |
| Engine tuning | see `services/worker/.env.example` | `SEG_CONF`, `MASK_DILATE`, `MIN/MAX_FONT_SIZE`, … inherited from the engine |

## Task kinds

| Kind | Does | Idempotency |
|---|---|---|
| `job.ingest` | Downloads uploads, validates them (`ingest.py`), reserves credits, stores pages | Status guard; deterministic keys |
| `page.prepare` | Detect → OCR (provider fallback) → filter → clean (LaMa or OpenCV) → render boxes | Skips when `stage != none` |
| `job.translate` | One batched, validated translation for all prepared pages | Only pages at `prepared` |
| `page.render` | Typesets onto the cleaned image, flags overflow | Skips ready/failed pages |
| `job.finalize` | Settles credits, final status, e-mail | Status guard + ledger keys |
| `page.typeset` | Editor re-render (free) | Discards the result if a newer edit exists (`version`) |
| `page.retranslate` / `page.reinpaint` | Paid single-page regeneration | Reservation keyed by page version |
| `job.archive` | Builds the chapter ZIP (served as .zip or .cbz) | Rebuilt when pages change |
| `job.purge`, `user.purge` | Deletes storage and scrubs content fields | Safe to repeat |
| `system.cleanup` | Hourly: expires jobs, prunes sessions/tokens/tasks/rate limits, cancels stale payments | Deduped per hour |
| `email.send` | Sends a transactional e-mail, then clears the payload (it may hold a one-time token) | — |

Failure handling: exceptions are retried with backoff up to 3 attempts. `tasks.Permanent` (bad user input) is
not retried. After the last attempt `tasks.on_dead` records the failure where users see it: the page is `failed`
(the chapter continues and can be retried), or the job is `FAILED` for ingest errors. Paid regenerations are
refunded. Users see only the code's safe message (`schemas.USER_ERRORS`). Technical detail stays in
`tasks.last_error` and the logs.

## Observability

JSON logs on stdout with `request_id` / `job_id` / `page_id`. No request bodies, images or secrets are logged.
`worker_heartbeats` holds one row per process (`last_seen_at`, current task, tasks done). The container
healthcheck fails if the process stops touching `/tmp/worker-alive` for 3 minutes. Queue depth and dead tasks are
in `/admin/metrics`.

## Tests

- `tests/test_units.py`: translation validation and malicious uploads (path traversal, zip bombs, fake
  extensions, truncated images, pixel and page caps). No models needed.
- `tests/test_e2e.py`: API + queue + worker + S3 (moto server) + real detection/inpainting/typesetting on two
  CC-BY sample pages. Covers the whole chapter lifecycle, editor re-typeset, downloads and bad uploads. Only the
  remote OCR/translation calls go to a local stub, because CI has no provider keys.

## Quality evaluation (go/no-go)

`scripts/try_samples.sh` runs the full engine (real OCR + translation with your API key) on
`samples/{cn,kr,ja}/input` and writes outputs plus token usage. Run it on your own real chapters before
launch. The CC-BY test pages are cleaner than typical manga (horizontal text, no screentone), so they are not a
quality benchmark.
