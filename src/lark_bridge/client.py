"""Main LarkBridge client class."""

from collections.abc import AsyncGenerator

from lark_bridge import listener, search, sender, drive


class LarkBridge:
    """High-level Feishu/Lark client using web cookie authentication."""

    def __init__(self, cookie: str):
        self._cookie = cookie.strip()
        self._cookies = self._parse_cookies(self._cookie)

    @staticmethod
    def _parse_cookies(cookie_str: str) -> dict[str, str]:
        return dict(item.split("=", 1) for item in cookie_str.split("; ") if "=" in item)

    async def listen(self, watch_chats: list[str] | None = None) -> AsyncGenerator[dict, None]:
        """Connect to WebSocket and yield Message dicts."""
        async for msg in listener.listen(self._cookie, self._cookies, watch_chats):
            yield msg

    async def search_messages(
        self,
        chat_id: str,
        start_time: int = 0,
        end_time: int = 0,
        from_id: str = "",
        mention_user_id: str = "",
        limit: int = 15,
    ) -> dict:
        """Search message IDs. Returns {"msg_ids": [...], "has_more": bool}."""
        return await search.search_msg_ids(self._cookie, chat_id, start_time, end_time, from_id, mention_user_id, limit)

    async def fetch_messages(self, msg_ids: list[str]) -> list[dict]:
        """Fetch message content by IDs."""
        return await search.fetch_messages(self._cookie, msg_ids)

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_id: str = "",
        at_user_ids: list[str] | None = None,
    ) -> bool:
        """Send a text message. Returns True on success."""
        return await sender.send_message(self._cookie, chat_id, text, reply_id, at_user_ids)

    async def create_folder(self, name: str, parent_token: str = "") -> dict | None:
        """Create a Drive folder. Returns {"token", "url"} or None."""
        return await drive.create_folder(self._cookie, self._cookies, name, parent_token)

    async def upload_file(self, folder_token: str, file_name: str, file_content: bytes) -> dict | None:
        """Upload a file to Drive. Returns {"file_token", "node_token"} or None."""
        return await drive.upload_file(self._cookie, self._cookies, folder_token, file_name, file_content)
