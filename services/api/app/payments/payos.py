"""payOS (VietQR bank transfer) — https://payos.vn/docs/api/
Signatures follow the official SDK (payOSHQ/payos-lib-python): HMAC-SHA256 with the checksum key over
`key=value` pairs sorted by key and joined with `&`; None/"null" become "".
"""

import hashlib
import hmac
import json
import time

import httpx

from .. import models as m
from ..config import get_settings
from .base import Checkout, InvalidSignature, ManualRefundRequired, ProviderEvent


def _query_string(data: dict) -> str:
    parts = []
    for key, value in sorted(data.items()):
        if isinstance(value, bool | int | float):
            s = str(value)
        elif value in (None, "null", "NULL"):
            s = ""
        elif isinstance(value, list):
            s = json.dumps([dict(sorted(i.items())) for i in value], separators=(",", ":")).replace("None", "null")
        else:
            s = str(value)
        parts.append(f"{key}={s}")
    return "&".join(parts)


def sign(data: dict, key: str) -> str:
    return hmac.new(key.encode(), _query_string(data).encode(), hashlib.sha256).hexdigest()


class PayOS:
    name = "payos"

    def __init__(self):
        s = get_settings()
        if not (s.payos_client_id and s.payos_api_key and s.payos_checksum_key):
            raise RuntimeError("PAYOS_CLIENT_ID / PAYOS_API_KEY / PAYOS_CHECKSUM_KEY are required for payOS")
        self.base_url, self.key = s.payos_base_url.rstrip("/"), s.payos_checksum_key
        self.headers = {"x-client-id": s.payos_client_id, "x-api-key": s.payos_api_key}

    def create_checkout(self, payment: m.Payment, product: m.Product, return_url: str, cancel_url: str) -> Checkout:
        signed = {"amount": payment.amount, "cancelUrl": cancel_url, "description": "MANGATL",
                  "orderCode": payment.order_code, "returnUrl": return_url}
        body = {**signed, "signature": sign(signed, self.key), "expiredAt": int(time.time()) + 15 * 60,
                "items": [{"name": product.name[:100], "quantity": 1, "price": payment.amount}]}
        r = httpx.post(f"{self.base_url}/v2/payment-requests", json=body, headers=self.headers, timeout=20)
        r.raise_for_status()
        res = r.json()
        if res.get("code") != "00":
            raise RuntimeError(f"payOS create failed: {res.get('code')} {res.get('desc')}")
        return Checkout(checkout_url=res["data"]["checkoutUrl"], provider_ref=res["data"].get("paymentLinkId"))

    def parse_webhook(self, body: bytes, headers: dict[str, str]) -> ProviderEvent:
        payload = json.loads(body)
        data, signature = payload.get("data") or {}, payload.get("signature") or ""
        if not hmac.compare_digest(sign(data, self.key), signature):
            raise InvalidSignature()
        ok = payload.get("code") == "00" and data.get("code") == "00"
        return ProviderEvent(
            event_id=f"{data.get('orderCode')}:{data.get('reference') or data.get('code')}",
            order_code=int(data["orderCode"]), status="paid" if ok else "failed",
            amount=int(data["amount"]) if data.get("amount") is not None else None,
            provider_ref=data.get("paymentLinkId"), raw=payload,
        )

    def fetch_status(self, payment: m.Payment) -> ProviderEvent:
        r = httpx.get(f"{self.base_url}/v2/payment-requests/{payment.order_code}", headers=self.headers, timeout=20)
        r.raise_for_status()
        data = r.json().get("data") or {}
        status = {"PAID": "paid", "CANCELLED": "cancelled", "EXPIRED": "cancelled"}.get(data.get("status"), "pending")
        return ProviderEvent(event_id=f"status:{payment.order_code}:{data.get('status')}", order_code=payment.order_code,
                             status=status, amount=data.get("amountPaid"), provider_ref=data.get("id"), raw=data)

    def refund(self, payment: m.Payment) -> None:
        raise ManualRefundRequired()
