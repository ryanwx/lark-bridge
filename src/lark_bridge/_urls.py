"""Centralized internal API host constants.

These are Feishu's internal service domains. They are fixed values
independent of the user-facing domain (e.g. ciloa.feishu.cn).
If Feishu changes these endpoints, update them here.
"""

INTERNAL_API = "https://internal-api-lark-api.feishu.cn"
DRIVE_STREAM = "https://internal-api-drive-stream.feishu.cn"
WS_FRONTIER = "wss://msg-frontier.feishu.cn"
LOGIN_HOST = "https://login.feishu.cn"


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)


# Feishu web client appKey (used for WebSocket access_key derivation)
# This rarely changes. If WS connection fails, may need updating.
APP_KEY = "5f45da0e6c7a17dcba80494ef0ab9b21"
