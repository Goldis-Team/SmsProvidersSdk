NAME = "melipayamak"

BASE_URL = "https://console.melipayamak.com/api"

SIMPLE_PATH = "/send/simple/{api_key}"
"""One text to one number. ``{from, to, text}``, all three required."""

ADVANCED_PATH = "/send/advanced/{api_key}"

SHARED_PATH = "/send/shared/{api_key}"
"""The pattern send. ``{bodyId, to, args: [...]}``; only ``to`` is required."""

MAX_BODY_ID = 2_147_483_647

PROBLEM_TITLE_KEY = "title"
PROBLEM_ERRORS_KEY = "errors"
