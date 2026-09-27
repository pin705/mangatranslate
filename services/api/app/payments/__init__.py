from functools import cache

from ..config import get_settings
from ..errors import AppError
from .base import PaymentProvider


@cache
def get_provider(name: str) -> PaymentProvider:
    if name not in get_settings().payment_providers:
        raise AppError(404, "NOT_FOUND", "Unknown payment provider.")
    if name == "payos":
        from .payos import PayOS
        return PayOS()
    if name == "dev":
        from .dev import DevProvider
        return DevProvider()
    raise AppError(404, "NOT_FOUND", "Unknown payment provider.")


def default_provider() -> PaymentProvider:
    return get_provider(get_settings().payment_providers[0])
