"""Melipayamak — endpoints and the fixed values its protocol defines.

This is the **console** API (``console.melipayamak.com``), not the older
``rest.payamak-panel.com`` one that Melipayamak's own PHP/Python/Node samples still use. The
console API is the one that takes an API key, accepts a real recipients *array* for a group send,
and answers with one id per recipient — the legacy API authenticates with a username and password,
takes recipients as a comma-joined string, and returns a single id for the whole batch.
"""

NAME = "melipayamak"

BASE_URL = "https://console.melipayamak.com/api"
"""The console API's root. Like Kavenegar and unlike SMS.ir, the credential is the **last path
segment** of every request — so every error message from this provider goes through
:func:`~sms_providers_sdk.common.utils.redact`."""

SIMPLE_PATH = "/send/simple/{api_key}"
"""One text to one number. ``{from, to, text}``, all three required."""

ADVANCED_PATH = "/send/advanced/{api_key}"
"""One text to many numbers. ``{from, to: [...], text, udh}`` — ``to`` is a genuine JSON array of
strings, and the response carries one id per entry."""

SHARED_PATH = "/send/shared/{api_key}"
"""The pattern send. ``{bodyId, to, args: [...]}``; only ``to`` is required."""

MAX_BODY_ID = 2_147_483_647
"""``bodyId`` is declared ``System.Int32``. Anything larger is rejected by the deserialiser before
Melipayamak's own code runs, with an error that talks about JSON conversion rather than about the
template."""

PROBLEM_TITLE_KEY = "title"
PROBLEM_ERRORS_KEY = "errors"
"""Melipayamak has **two** failure shapes, and they disagree about what ``status`` means.

An application-level refusal — bad key, no credit — is ``{"status": "<Persian text>"}`` with the
``recId`` key *absent*. A malformed request never reaches that code: ASP.NET Core's model binder
rejects it first and answers RFC 7807 ProblemDetails, where ``status`` is the **integer** ``400``
and the useful part is ``title`` plus ``errors``. Reading ``status`` as text in that case yields
the message ``"400"``, which explains nothing, so the two are told apart by these keys.
"""
