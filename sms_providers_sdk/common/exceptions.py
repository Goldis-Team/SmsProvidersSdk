from typing import Any


class SmsError(Exception):
    """Base for everything this SDK raises."""


class ConfigurationError(SmsError):
    pass


class NetworkError(SmsError):
    """The provider could not be reached, timed out, or answered with something undecodable."""


class ProviderError(SmsError):
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
    pass
