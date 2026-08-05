"""One error hierarchy across every provider.

Sending is a **request-path** operation: there is no callback, no returning customer, and nothing
to reconcile later. So a send that did not happen raises, rather than returning a result object
whose ``success`` flag a caller can forget to read. What comes back from a successful send is a
description of what the provider accepted — see
:class:`~sms_providers_sdk.common.data.SmsResult` — not a verdict you have to test.

Per-recipient outcomes are a different thing entirely. A provider accepts a batch and reports
delivery per number *later*; those statuses arrive on each
:class:`~sms_providers_sdk.common.data.SentMessage` and are data, not errors.
"""

from typing import Any


class SmsError(Exception):
    """Base for everything this SDK raises."""


class ConfigurationError(SmsError):
    """The provider cannot be addressed as configured, or the message cannot be built.

    Raised at construction, or as soon as a required field is found unusable — before any network
    call, so an empty text or a malformed recipient fails while you are wiring it up rather than
    coming back as a numeric provider code that explains nothing.
    """


class NetworkError(SmsError):
    """The provider could not be reached, timed out, or answered with something undecodable."""


class ProviderError(SmsError):
    """The provider was reached and refused the call.

    Invalid API key, insufficient credit, a sender line you do not own, a template that does not
    exist. ``code`` is the provider's own status value, unchanged.
    """

    def __init__(
        self,
        message: str,
        *,
        code: Any = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        """The provider's own status code, as it sent it."""
        self.raw = raw or {}
        """The provider's decoded response, untouched."""


class UnsupportedOperation(SmsError):
    """This provider does not offer the operation that was called.

    All three of send, bulk send and pattern send exist on both engine protocols so that call
    sites do not branch on provider name. A provider that genuinely lacks one raises this instead
    of silently doing something adjacent — sending a rendered template as a plain message, say,
    which bills at a different rate and bypasses the recipient's opt-in for service messages.
    """
