"""Every provider, plus a registry for picking one by name at runtime.

Each provider directory holds the same five things: ``constants.py`` (endpoints and the fixed
values its protocol defines), ``data.py`` (credentials and the provider's own result records —
dataclasses only), ``helpers.py`` (the pure functions that build payloads and read responses), and
``sync_engine.py`` / ``async_engine.py``, which are thin shells over both. That split is why the
two engines cannot drift apart: every decision about what a provider said lives in ``helpers.py``
and is shared, so only the transport call differs.

The registry holds **classes, not instances**. A shared instance can carry exactly one account's
credentials, so build one per account with :func:`get_sync_provider` / :func:`get_async_provider`
rather than caching a provider globally.
"""

from typing import Any

from sms_providers_sdk.common.exceptions import ConfigurationError
from sms_providers_sdk.common.interfaces import IAsyncSmsProvider, ISyncSmsProvider
from sms_providers_sdk.providers.kavenegar import KavenegarAsync as KavenegarAsync
from sms_providers_sdk.providers.kavenegar import KavenegarConfig as KavenegarConfig
from sms_providers_sdk.providers.kavenegar import KavenegarDetails as KavenegarDetails
from sms_providers_sdk.providers.kavenegar import KavenegarSync as KavenegarSync

SYNC_PROVIDERS: dict[str, type[ISyncSmsProvider]] = {
    "kavenegar": KavenegarSync,
}

ASYNC_PROVIDERS: dict[str, type[IAsyncSmsProvider]] = {
    "kavenegar": KavenegarAsync,
}


def available() -> tuple[str, ...]:
    """Every provider name, sorted. The same names work in both engines."""
    return tuple(sorted(SYNC_PROVIDERS))


def get_sync_provider(name: str, **credentials: Any) -> ISyncSmsProvider:
    """Build a sync provider by name, e.g. ``get_sync_provider("kavenegar", api_key="…")``."""
    try:
        provider_cls = SYNC_PROVIDERS[name]
    except KeyError:
        raise ConfigurationError(
            f"unknown provider {name!r} — available: {', '.join(available())}"
        ) from None
    return provider_cls(**credentials)


def get_async_provider(name: str, **credentials: Any) -> IAsyncSmsProvider:
    """Build an async provider by name, e.g. ``get_async_provider("kavenegar", api_key="…")``."""
    try:
        provider_cls = ASYNC_PROVIDERS[name]
    except KeyError:
        raise ConfigurationError(
            f"unknown provider {name!r} — available: {', '.join(available())}"
        ) from None
    return provider_cls(**credentials)
