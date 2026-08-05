"""Kavenegar — endpoints and the fixed values its protocol defines."""

NAME = "kavenegar"

BASE_URL = "https://api.kavenegar.com/v1/{api_key}/{scope}/{method}.json"
"""Kavenegar authenticates by **path**, not by header: the API key is a URL segment.

That is why every error message from this provider goes through
:func:`~sms_providers_sdk.common.utils.redact` — the URL appears verbatim in the exceptions both
HTTP clients raise, and would otherwise land in logs with the key in it.
"""

SEND = ("sms", "send")
"""One text to one or many recipients, comma-separated. This is the group send: ``sendarray`` is
for a *different* text per recipient, which is a different operation and not what
:class:`~sms_providers_sdk.common.data.BulkSmsMessage` models."""

LOOKUP = ("verify", "lookup")
"""The pattern send. Kavenegar calls templates "verify lookup" because the feature grew out of
one-time codes, but it is the general template channel."""

SUCCESS_STATUS = 200
"""The value of ``return.status`` that means the call was accepted."""

MAX_RECIPIENTS = 200
"""Recipients per ``sms/send`` call. Checked before sending: over the cap Kavenegar rejects the
batch with 414 and **nothing** goes out, so a caller who does not split gets total silence."""

MAX_MESSAGE_LENGTH = 1800
"""Characters per message on a shared line. Internal (dedicated) lines allow 4000, but the SDK
cannot tell which kind of line an account holds, so it checks against the limit that applies to
every account. Pass ``extra={"maxlength": …}`` — or simply exceed this on a dedicated line by
raising it yourself — if you know you have the longer allowance."""

MAX_TOKENS = 20
"""``%token`` through ``%token20``."""

MAX_TOKEN_LENGTH = 100
"""Characters per token value."""

SPACES_ALLOWED_IN = frozenset({"token10", "token20"})
"""The only two token slots that accept whitespace.

Every other token is rejected — Kavenegar's parser treats the value as a single URL token — and the
error it returns says nothing about spaces. It is the single most common way a pattern send fails,
so it is checked here with a message that names the offending slot.
"""

RETURN_STATUSES = {
    200: "approved",
    400: "parameters are incomplete",
    401: "account is deactivated",
    402: "the operation failed",
    403: "invalid API key",
    404: "method not found",
    405: "wrong HTTP method (GET/POST)",
    406: "a required parameter was sent empty",
    407: "access to this data is not permitted",
    409: "server unavailable — retry shortly",
    411: "invalid recipient number",
    412: "invalid sender number",
    413: "message empty, or longer than the line allows",
    414: "request volume exceeded (200 per send, 500 per status call)",
    415: "start index is larger than the total",
    416: "the calling IP does not match the account settings",
    417: "invalid date",
    418: "insufficient credit",
    419: "the receptor, sender and message arrays are not the same length",
    420: "links may not be used with this account",
    422: "the message could not be encoded — check the character set",
    424: "template not found",
    426: "this method requires the advanced service plan",
    427: "this line needs an access level configured",
    428: "voice call is not available for this message",
    429: "the calling IP is blocked",
    431: "invalid code structure",
    432: "the code parameter is missing from the template",
    451: "rate limit exceeded — too many identical calls",
    501: "in test mode, messages go only to the account owner",
    604: "too many numbers submitted",
    607: "invalid tag name",
}
"""Kavenegar's ``return.status`` values, in English.

Kavenegar sends its own Persian ``return.message`` alongside the code; that text is preserved
verbatim on :attr:`~...KavenegarDetails.return_message` and in ``raw``. This table exists so that
an exception raised in a service with no Persian in it still says what went wrong.
"""

MESSAGE_STATUSES = {
    1: "queued",
    2: "scheduled",
    4: "sent to the operator",
    5: "sent to the operator",
    6: "failed at the operator",
    10: "delivered to the recipient",
    11: "not delivered — handset off or blocked",
    13: "cancelled",
    14: "blocked by the recipient",
    100: "invalid message id",
}
"""Per-message state. At send time this is 1 or 2; everything past that arrives minutes later, via
a delivery-status call or Kavenegar's webhook, and is not something a send can report."""

MESSAGE_TYPES = {
    0: "flash — shown immediately, not stored",
    1: "normal — stored on the handset",
    2: "stored on the SIM",
    3: "delivered to an application",
}
"""Values for the optional ``type`` parameter, passed through ``extra``."""
