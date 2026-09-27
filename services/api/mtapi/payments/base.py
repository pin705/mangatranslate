from dataclasses import dataclass
from typing import Literal, Protocol

from .. import models as m


class InvalidSignature(Exception):
    pass


class ManualRefundRequired(Exception):
    """The provider has no refund API (e.g. VietQR bank transfers); refund out-of-band, then record it."""


@dataclass
class Checkout:
    checkout_url: str
    provider_ref: str | None = None


@dataclass
class ProviderEvent:
    event_id: str  # unique per provider; dedupes webhook retries
    order_code: int
    status: Literal["paid", "cancelled", "failed", "pending", "ignored"]
    amount: int | None
    provider_ref: str | None
    raw: dict


class PaymentProvider(Protocol):
    name: str

    def create_checkout(self, payment: m.Payment, product: m.Product, return_url: str, cancel_url: str) -> Checkout: ...

    def parse_webhook(self, body: bytes, headers: dict[str, str]) -> ProviderEvent:
        """Verify the signature and normalise the payload. Raises InvalidSignature."""
        ...

    def fetch_status(self, payment: m.Payment) -> ProviderEvent:
        """Ask the provider directly (server-to-server) — used to reconcile missed webhooks."""
        ...

    def refund(self, payment: m.Payment) -> None: ...
