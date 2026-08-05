"""SMS.ir — endpoints and the fixed values its protocol defines."""

NAME = "smsir"

BASE_URL = "https://api.sms.ir/v1"
"""Every method hangs off this. Unlike Kavenegar, the credential is a **header**
(:data:`API_KEY_HEADER`) rather than a path segment, so the URL is safe to log."""

API_KEY_HEADER = "X-API-KEY"

BULK_PATH = "/send/bulk"
"""One text to up to 100 numbers. Also where a single send goes: SMS.ir has no plain
one-recipient endpoint for free-form text — the only alternative is a legacy ``GET /send`` that
authenticates with a username and password instead of the API key, which is a different credential
and a deprecated route."""

VERIFY_PATH = "/send/verify"
"""The pattern send. SMS.ir calls it "verify" because it grew out of one-time codes, but it is the
general template channel — and the only one that reaches numbers on the platform's blacklist."""

SUCCESS_STATUS = 1
"""The value of the response's ``status`` field that means the call was accepted. Note that this
is ``1``, not ``200`` — the resemblance to an HTTP status is a coincidence, and SMS.ir sends a
*separate* HTTP status alongside it."""

MAX_RECIPIENTS = 100
"""Numbers per ``send/bulk`` call — half Kavenegar's allowance. Checked before sending, because an
oversized batch is rejected whole (status 105) and none of it goes out."""

MAX_PARAMETER_LENGTH = 25
"""Characters per template parameter *value* (status 114).

Short enough to matter: a full name, an order title or a product name will overrun it, and the
resulting failure is a numeric code with no indication of which parameter was too long.
"""

MIN_SCHEDULE_AHEAD = 3600
"""Seconds. ``sendDateTime`` must be at least an hour out and at most a year (status 109).

Documented rather than enforced: checking it needs a clock, and a client whose time is a few
minutes off would then have legitimate sends refused locally — a worse failure than the provider's
own, which at least reflects the provider's clock.
"""

MAX_SCHEDULE_AHEAD = 365 * 24 * 3600
"""Seconds. The far end of the same window."""

STATUSES = {
    0: "a system error occurred at SMS.ir",
    1: "successful",
    10: "invalid API key",
    11: "the API key is deactivated",
    12: "the API key is restricted to other IP addresses",
    13: "the account is deactivated",
    14: "the account is suspended",
    20: "too many requests — rate limit exceeded",
    101: "invalid line number",
    102: "insufficient credit",
    103: "the request contains empty message text",
    104: "the request contains invalid mobile numbers",
    105: "too many mobile numbers (the limit is 100)",
    106: "too many message texts (the limit is 100)",
    107: "the mobile number list is empty",
    108: "the message text list is empty",
    109: "invalid send time",
    110: "the mobile number count and the message count differ",
    111: "no send was recorded under that pack id",
    112: "no record found to delete",
    113: "template not found",
    114: "a parameter value is longer than the 25-character limit",
    115: "the mobile number(s) are on the platform blacklist",
    116: "a parameter name is empty",
    117: "the message text is not approved",
    118: "too many messages",
    119: "custom templates need a higher plan",
    123: "the sending line needs to be activated",
}
"""SMS.ir's ``status`` values, in English.

SMS.ir sends its own Persian ``message`` alongside the code; that text is preserved verbatim on
:attr:`~...SmsIrDetails.status_message` and in ``raw``. This table exists so that an exception
raised in a service with no Persian in it still says what went wrong.
"""

BLACKLIST_STATUS = 115
"""Worth singling out: this is the one refusal that is about the *recipient* rather than the
account or the request, and the fix is a pattern send — service lines reach blacklisted numbers."""
