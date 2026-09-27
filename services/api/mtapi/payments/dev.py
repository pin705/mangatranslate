"""Local/test payment provider. Its "checkout" is an API-served page whose buttons post a webhook signed with
DEV_PAYMENT_SECRET to the normal webhook endpoint, so credits still flow only through verified webhook processing.
Settings.check() refuses to boot production with this provider enabled."""

import hashlib
import hmac
import json

from .. import models as m
from ..config import get_settings
from .base import Checkout, InvalidSignature, ProviderEvent


def sign(body: bytes) -> str:
    return hmac.new(get_settings().dev_payment_secret.encode(), body, hashlib.sha256).hexdigest()


class DevProvider:
    name = "dev"

    def create_checkout(self, payment: m.Payment, product: m.Product, return_url: str, cancel_url: str) -> Checkout:
        return Checkout(checkout_url=f"/api/v1/billing/dev/checkout/{payment.id}", provider_ref=f"dev-{payment.order_code}")

    def parse_webhook(self, body: bytes, headers: dict[str, str]) -> ProviderEvent:
        if not hmac.compare_digest(sign(body), headers.get("x-dev-signature", "")):
            raise InvalidSignature()
        data = json.loads(body)
        return ProviderEvent(event_id=data["event_id"], order_code=int(data["order_code"]), status=data["status"],
                             amount=data.get("amount"), provider_ref=data.get("provider_ref"), raw=data)

    def fetch_status(self, payment: m.Payment) -> ProviderEvent:
        return ProviderEvent(event_id=f"status:{payment.order_code}", order_code=payment.order_code, status="pending",
                             amount=None, provider_ref=None, raw={})

    def refund(self, payment: m.Payment) -> None:
        return None
