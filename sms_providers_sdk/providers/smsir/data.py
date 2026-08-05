"""SMS.ir — credentials and the records SMS.ir itself returns.

Dataclasses only. Endpoints and fixed values live in ``constants.py``; the functions that build
payloads and read responses live in ``helpers.py``.

Contract (REST, JSON in and out): ``POST https://api.sms.ir/v1/{method}`` with the API key in an
``X-API-KEY`` header. Every response has the same three-part shape::

    {"status": 1, "message": "موفق", "data": {…}}

``status`` is ``1`` for accepted and a code from
:data:`~sms_providers_sdk.providers.smsir.constants.STATUSES` otherwise. ``data`` differs per
method: ``{packId, messageIds, cost}`` for a bulk send, ``{messageId, cost}`` for a pattern send.

Three differences from Kavenegar are worth knowing before reading the rest:

* **The line number is required.** There is no account-level default the API falls back to, so
  either the provider is built with ``line_number=…`` or every message carries a ``sender``.
* **There is no per-recipient result.** A bulk send answers with a flat list of message ids in the
  order the numbers were submitted, and one cost for the whole call — no echoed numbers, no
  per-message status. The recipients on :class:`~sms_providers_sdk.common.data.SentMessage` are
  therefore the ones *sent*, paired back by position.
* **Template parameters are named, not positional.** SMS.ir placeholders are ``#NAME#``, and the
  API takes ``[{"name": …, "value": …}]``. A positional token sequence has nothing to map onto.
"""

from dataclasses import dataclass, field

from sms_providers_sdk.common.data import ProviderDetails


@dataclass(frozen=True)
class SmsIrConfig:
    """SMS.ir credentials.

    ``api_key`` is the key from the developer panel. It is excluded from ``repr`` because this
    object ends up in tracebacks and debugger frames, and the key is a bearer credential: anyone
    holding it can send messages billed to the account.
    """

    api_key: str = field(repr=False)

    line_number: str = ""
    """The default sending line. SMS.ir requires one on every free-form send and offers no
    server-side fallback, so leaving this empty means each :class:`SmsMessage
    <sms_providers_sdk.common.data.SmsMessage>` has to carry its own ``sender``."""


@dataclass(frozen=True)
class SmsIrDetails(ProviderDetails):
    """What SMS.ir said about the call as a whole.

    Present on every successful :class:`~sms_providers_sdk.common.data.SmsResult`, and on the
    :class:`~sms_providers_sdk.common.exceptions.ProviderError` raised when SMS.ir refused.
    """

    status: int | None = None
    """SMS.ir's ``status``. ``1`` is the only value that means accepted."""

    status_message: str | None = None
    """SMS.ir's own text for that status, in Persian, exactly as sent."""

    status_description: str | None = None
    """The same status in English, from
    :data:`~sms_providers_sdk.providers.smsir.constants.STATUSES`."""

    pack_id: str | None = None
    """The batch's id, on a bulk send.

    Worth storing whenever ``send_at`` was used: cancelling a scheduled send is
    ``DELETE /send/scheduled/{packId}``, and the per-message ids will not do it.
    """
