"""SMS.ir — endpoints and the fixed values its protocol defines."""

NAME = "smsir"

BASE_URL = "https://api.sms.ir/v1"

API_KEY_HEADER = "X-API-KEY"

BULK_PATH = "/send/bulk"

VERIFY_PATH = "/send/verify"

SUCCESS_STATUS = 1

MAX_RECIPIENTS = 100

MAX_PARAMETER_LENGTH = 25

MIN_SCHEDULE_AHEAD = 3600

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

BLACKLIST_STATUS = 115
