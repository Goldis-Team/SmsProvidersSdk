"""Constants shared across every provider and both engines.

Values that are facts about a *specific* provider — its endpoints, its success codes, how many
recipients it takes per call — live in that provider's own ``constants.py``. Only what genuinely
applies everywhere belongs here.
"""

DEFAULT_TIMEOUT = 15.0
"""Seconds. Long enough for a sluggish SMS gateway, short enough that a dead one is not a hung
worker. Sending an SMS is usually a side effect of a request the user is waiting on, so the ceiling
matters more here than the occasional retry."""

REDACTED = "***"
"""What an API key is replaced with before it reaches an error message or a log line."""
