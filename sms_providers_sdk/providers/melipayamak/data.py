"""Melipayamak — credentials and the records Melipayamak itself returns.

Dataclasses only. Endpoints and fixed values live in ``constants.py``; the functions that build
payloads and read responses live in ``helpers.py``.

Contract (REST, JSON both ways): ``POST https://console.melipayamak.com/api/{method}/{apikey}``.
The key is the last path segment — a credential in the URL, as with Kavenegar.

Responses carry the ids and a ``status``::

    {"recId": 3741437414, "status": …}      # send/simple, send/shared
    {"recIds": [3741437414, …], "status": …} # send/advanced

**``status`` is an error description, not a success code.** Melipayamak's own documentation labels
it ``"شرح خطا در صورت بروز"`` — "description of the error, if one occurs" — and a refusal answers
HTTP 400 with ``{"status": "کلید کنسول معتبر نیست"}`` and no ``recId`` key at all. So success here
is decided by *the id being there*, never by matching ``status`` against a value. This SDK does not
know what ``status`` holds on a successful send, and does not need to.

Three differences from the other providers:

* **No numeric error codes.** Kavenegar has 418, SMS.ir has 102; Melipayamak has a Persian
  sentence. :attr:`ProviderError.code <sms_providers_sdk.common.exceptions.ProviderError.code>` is
  therefore ``None`` for this provider, and the message is what carries the meaning.
* **No cost, anywhere.** Neither send reports one, so :attr:`SmsResult.cost
  <sms_providers_sdk.common.data.SmsResult.cost>` is always ``None``. Credit is a separate
  endpoint.
* **No scheduling on these endpoints.** Melipayamak has a separate ``send/schedule`` method, so
  ``send_at`` is refused rather than dropped.
"""

from dataclasses import dataclass, field

from sms_providers_sdk.common.data import ProviderDetails


@dataclass(frozen=True)
class MelipayamakConfig:
    """Melipayamak console credentials.

    ``api_key`` is the console key, from ``console.melipayamak.com``. It is excluded from ``repr``
    because this object ends up in tracebacks and debugger frames, and the key is a bearer
    credential: anyone holding it can send messages billed to the account.
    """

    api_key: str = field(repr=False)

    sender: str = ""
    """The default sending line. Required by ``send/simple`` and ``send/advanced`` — not by the
    pattern send, whose line belongs to the template."""


@dataclass(frozen=True)
class MelipayamakDetails(ProviderDetails):
    """What Melipayamak said about the call as a whole.

    Present on every successful :class:`~sms_providers_sdk.common.data.SmsResult`, and on the
    :class:`~sms_providers_sdk.common.exceptions.ProviderError` raised when Melipayamak refused.
    """

    status_message: str | None = None
    """Melipayamak's ``status`` field, verbatim.

    On a refusal this is the Persian explanation and the only thing that says what went wrong. On
    a successful send it is whatever Melipayamak chooses to put there — the API documents the field
    only as an error description, so treat a value here as informational, never as confirmation.
    """

    rec_ids: tuple[str, ...] = ()
    """Every id the call returned, as strings.

    Melipayamak's ids are 64-bit and already exceed ``int32`` in its own examples. Python's
    integers are arbitrary-precision so nothing is lost in parsing — a JavaScript client has to
    reach for a bigint library to avoid corrupting ids past 2^53 — but they are carried as strings
    here so that they survive being written to JSON by whatever consumes this.
    """
