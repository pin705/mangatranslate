"""AI provider calls: registry from the `providers` table, fallback, cost accounting, budget cap, and
validated chapter translation. Every provider speaks the OpenAI-compatible chat API (OpenAI, DeepSeek,
Gemini's OpenAI endpoint, OpenRouter, DashScope/Qwen…), so one adapter covers them; adding a non-compatible
vendor means adding a branch in `_chat`.
"""

import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

import requests
from sqlalchemy import func, select, text

from mtapi import app_settings
from mtapi import models as m
from mtapi.db import session_scope

log = logging.getLogger("worker.ai")

_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯ᄀ-ᇿ]")
BATCH = 120


class BudgetExceeded(Exception):
    pass


class ProvidersUnavailable(Exception):
    pass


@dataclass
class Provider:
    id: object
    name: str
    base_url: str
    model: str
    api_key: str
    price_in: Decimal
    price_out: Decimal


def seed_providers() -> None:
    """First boot: create provider rows from the environment. Afterwards the table (admin UI) is authoritative."""
    openai_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    rows = [
        ("translation", "primary", os.environ.get("TRANSLATION_BASE_URL", openai_base),
         os.environ.get("TRANSLATION_MODEL", os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")),
         os.environ.get("TRANSLATION_API_KEY_ENV", "OPENAI_API_KEY"), 10, "0.75", "4.50"),
        ("ocr", "primary", os.environ.get("OCR_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
         os.environ.get("OCR_MODEL", "qwen3-vl-flash"), os.environ.get("OCR_API_KEY_ENV", "DASHSCOPE_API_KEY"),
         10, "0.10", "0.40"),
    ]
    if os.environ.get("TRANSLATION_FALLBACK_BASE_URL"):
        rows.append(("translation", "fallback", os.environ["TRANSLATION_FALLBACK_BASE_URL"],
                     os.environ.get("TRANSLATION_FALLBACK_MODEL", "deepseek-chat"),
                     os.environ.get("TRANSLATION_FALLBACK_API_KEY_ENV", "DEEPSEEK_API_KEY"), 20, "0.27", "1.10"))
    with session_scope() as db:
        if db.execute(select(func.count()).select_from(m.Provider)).scalar_one():
            return
        for kind, name, url, model, key_env, prio, pin, pout in rows:
            db.add(m.Provider(kind=kind, name=name, base_url=url.rstrip("/"), model=model, api_key_env=key_env,
                              priority=prio, input_price_per_1m=Decimal(pin), output_price_per_1m=Decimal(pout)))


def providers(kind: str) -> list[Provider]:
    with session_scope() as db:
        rows = db.execute(select(m.Provider).where(m.Provider.kind == kind, m.Provider.enabled)
                          .order_by(m.Provider.priority)).scalars().all()
        healthy = [r for r in rows if r.consecutive_failures < 5] or rows  # circuit breaker, never zero options
        out = [Provider(r.id, r.name, r.base_url, r.model, os.environ.get(r.api_key_env, ""), r.input_price_per_1m,
                        r.output_price_per_1m) for r in healthy]
    out = [p for p in out if p.api_key]
    if not out:
        raise ProvidersUnavailable(f"no enabled {kind} provider with an API key")
    return out


def check_budget() -> None:
    with session_scope() as db:
        cap = Decimal(str(app_settings.get(db, "max_monthly_ai_spend_usd")))
        spent = db.execute(text("SELECT coalesce(sum(cost_usd), 0) FROM provider_usage "
                                "WHERE created_at >= date_trunc('month', now())")).scalar_one()
    if spent >= cap:
        raise BudgetExceeded(f"monthly AI budget reached ({spent} >= {cap} USD)")


def record(p: Provider, ctx: dict, operation: str, usage: dict, ms: int, ok: bool, uncertain: bool = False,
           error: str | None = None) -> None:
    pin, pout = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    cost = (Decimal(pin) * p.price_in + Decimal(pout) * p.price_out) / Decimal(1_000_000)
    with session_scope() as db:
        db.add(m.ProviderUsage(user_id=ctx.get("user_id"), job_id=ctx.get("job_id"), page_id=ctx.get("page_id"),
                               provider=p.name, model=p.model, operation=operation, input_units=pin, output_units=pout,
                               duration_ms=ms, cost_usd=cost, success=ok, uncertain=uncertain))
        row = db.get(m.Provider, p.id)
        if row:
            row.consecutive_failures = 0 if ok else row.consecutive_failures + 1
            row.last_error = None if ok else (error or "")[:1000]


# --- OCR -------------------------------------------------------------------------------

def ocr(image, blocks, source_lang: str, ctx: dict) -> None:
    """Fill block.text using the first OCR provider that works."""
    from modules.ocr.qwen_grid_ocr import QwenGridOCR

    check_budget()
    last: Exception | None = None
    for p in providers("ocr"):
        engine = QwenGridOCR()
        engine.initialize(api_key=p.api_key, model=p.model, source_lang=source_lang)
        engine.api_base_url = f"{p.base_url}/chat/completions"
        before = len(QwenGridOCR._usage_events)
        started = time.monotonic()
        try:
            engine.process_image(image, blocks)
        except Exception as e:  # HTTP error / timeout: try the next provider
            last = e
            record(p, ctx, "ocr", {}, int((time.monotonic() - started) * 1000), ok=False,
                   uncertain=isinstance(e, requests.Timeout), error=str(e))
            log.warning("ocr provider %s failed: %s", p.name, e)
            continue
        usage = QwenGridOCR._usage_events[-1] if len(QwenGridOCR._usage_events) > before else {}
        record(p, ctx, "ocr", usage, int((time.monotonic() - started) * 1000), ok=True)
        del QwenGridOCR._usage_events[:]  # the engine keeps a class-level list; we already recorded it
        return
    raise ProvidersUnavailable(f"all OCR providers failed: {last}")


# --- translation ------------------------------------------------------------------------

STYLE = {
    "Vietnamese": ("Write natural, fluent Vietnamese as a professional manga/manhwa translator would. Choose "
                   "pronouns (tôi/cậu, anh/em, ta/ngươi, huynh/muội…) that fit the characters' relationship and the "
                   "genre (Sino-Vietnamese forms for xianxia/wuxia). Keep them consistent across the chapter."),
    "English": "Write natural, fluent English dialogue as a professional localizer would.",
}


def _system(source: str, target: str, glossary: list[dict]) -> str:
    rules = [
        f"You translate {source} comic text (OCR'd, may contain small errors) into {target}.",
        STYLE.get(target, ""),
        "Keep character names, places and terms consistent with the glossary and previous lines.",
        "Preserve the tone: shouting stays emphatic, whispers stay soft. Keep it short enough to fit a speech bubble.",
        "Keep placeholders such as {name}, %s or [1] unchanged. Do not add notes or explanations.",
        'Reply with JSON only: {"translations": {"<id>": "<translation>", ...}} containing exactly the given ids.',
    ]
    if glossary:
        terms = "\n".join(f"- {g['source']} → {g['target']}" for g in glossary)
        rules.append(f"Always use these translations:\n{terms}")
    return "\n".join(r for r in rules if r)


def _chat(p: Provider, system: str, user: str) -> tuple[dict, dict]:
    r = requests.post(
        f"{p.base_url}/chat/completions", timeout=180,
        headers={"Authorization": f"Bearer {p.api_key}", "Content-Type": "application/json"},
        data=json.dumps({"model": p.model, "temperature": 0.3, "response_format": {"type": "json_object"},
                         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}),
    )
    r.raise_for_status()
    body = r.json()
    content = body["choices"][0]["message"]["content"] or ""
    return json.loads(content), body.get("usage") or {}


def _placeholders(s: str) -> list[str]:
    return sorted(re.findall(r"\{\w+\}|%[sd]|\[\d+\]", s))


def validate(batch: dict[str, str], reply: dict, target: str) -> tuple[dict[str, str], set[str], set[str]]:
    """Returns (accepted, ids to retry, ids accepted but flagged for review)."""
    out = reply.get("translations") if isinstance(reply, dict) else None
    if not isinstance(out, dict):
        return {}, set(batch), set()
    accepted, retry, flagged = {}, set(), set()
    for key, src in batch.items():
        t = out.get(key)
        if not isinstance(t, str) or not t.strip() or "�" in t:
            retry.add(key)
            continue
        t = unicodedata.normalize("NFC", t.strip())
        if target in ("Vietnamese", "English") and _CJK.search(src) and len(_CJK.findall(t)) > len(t) * 0.3:
            retry.add(key)  # left untranslated
            continue
        if len(t) > 6 * len(src) + 40 or _placeholders(t) != _placeholders(src):
            flagged.add(key)
        accepted[key] = t
    return accepted, retry, flagged


def translate(lines: dict[str, str], source: str, target: str, glossary: list[dict], ctx: dict,
              attempts: int = 3) -> tuple[dict[str, str], set[str]]:
    """Translate {id: text} in chapter order. Returns (translations, ids needing review). Missing ids are
    retried, then the next provider is tried; ids still missing are returned absent (flagged by the caller)."""
    system = _system(source, target, glossary)
    done: dict[str, str] = {}
    flagged: set[str] = set()
    keys = list(lines)
    for start in range(0, len(keys), BATCH):
        pending = {k: lines[k] for k in keys[start:start + BATCH]}
        for p in providers("translation"):
            for _ in range(attempts):
                if not pending:
                    break
                check_budget()
                previous = [{"source": lines[k], "translation": done[k]} for k in list(done)[-15:]]
                user = json.dumps({"previous_lines": previous, "lines": [{"id": k, "text": v} for k, v in pending.items()]},
                                  ensure_ascii=False)
                started = time.monotonic()
                try:
                    reply, usage = _chat(p, system, user)
                except (requests.RequestException, ValueError, KeyError, IndexError) as e:
                    record(p, ctx, "translation", {}, int((time.monotonic() - started) * 1000), ok=False,
                           uncertain=isinstance(e, requests.Timeout | ValueError), error=str(e))
                    log.warning("translation provider %s failed: %s", p.name, e)
                    break  # next provider
                record(p, ctx, "translation", usage, int((time.monotonic() - started) * 1000), ok=True)
                ok, retry, warn = validate(pending, reply, target)
                done.update(ok)
                flagged |= warn
                pending = {k: pending[k] for k in retry}
            if not pending:
                break
        flagged |= set(pending)
    return done, flagged
