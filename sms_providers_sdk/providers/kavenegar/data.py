"""Kavenegar — credentials and the records Kavenegar itself returns.

Dataclasses only. Endpoints and fixed values live in ``constants.py``; the functions that build
payloads and read responses live in ``helpers.py``.

Contract (REST, form-encoded in / JSON out): every call is
``POST https://api.kavenegar.com/v1/{API-KEY}/{scope}/{method}.json``. The API key is a path
segment, so it is a credential in the URL — see :func:`~sms_providers_sdk.common.utils.redact`.

Every response has the same two-part shape::

    {"return": {"status": 200, "message": "تایید شد"},
     "entries": [{"messageid": …, "status": 1, "receptor": …, "cost": …}, …]}

``return.status`` is whether the *call* was accepted; ``entries`` is one record per recipient.
``entries`` is a list for the send methods and a bare object for ``verify/lookup`` — both shapes
are read here. On a rejected call Kavenegar mirrors the status into the HTTP status too, and
``entries`` is absent or null.

Three operations are wired up: :meth:`send <…KavenegarSync.send>` (``sms/send``),
:meth:`send_bulk <…KavenegarSync.send_bulk>` (``sms/send`` with comma-separated recipients) and
:meth:`send_pattern <…KavenegarSync.send_pattern>` (``verify/lookup``).
"""

from dataclasses import dataclass, field

from sms_providers_sdk.common.data import ProviderDetails


@dataclass(frozen=True)
class KavenegarConfig:
    """Kavenegar credentials.

    ``api_key`` is the key from the panel's API section. It is excluded from ``repr`` because this
    object ends up in tracebacks and debugger frames, and the key is a bearer credential: anyone
    holding it can send messages billed to the account.
    """

    api_key: str = field(repr=False)

    sender: str = ""
    """The default line to send from. Empty means "let Kavenegar pick", which uses the account's
    configured default sender — the usual setup, and the reason this is optional."""


@dataclass(frozen=True)
class KavenegarDetails(ProviderDetails):
    """The ``return`` object of a Kavenegar response — what it said about the call as a whole.

    Present on every successful :class:`~sms_providers_sdk.common.data.SmsResult`, and on the
    :class:`~sms_providers_sdk.common.exceptions.ProviderError` raised when Kavenegar refused. The
    per-recipient records are on :attr:`SmsResult.messages <…SmsResult.messages>`.
    """

    return_status: int | None = None
    """Kavenegar's ``return.status``. ``200`` is the only value that means accepted."""

    return_message: str | None = None
    """Kavenegar's own text for that status, in Persian, exactly as sent."""

    status_description: str | None = None
    """The same status in English, from
    :data:`~sms_providers_sdk.providers.kavenegar.constants.RETURN_STATUSES` — so a log line in a
    service that has no Persian in it still says what happened."""
