"""Main LarkBridge client class."""

from collections.abc import AsyncGenerator

from lark_bridge import listener, search, sender, drive


class LarkBridge:
    """High-level Feishu/Lark client using web cookie authentication."""

    def __init__(self, cookie: str, domain: str = "www.feishu.cn"):
        self._cookie = cookie.strip()
        self._cookies = self._parse_cookies(self._cookie)
        self._domain = domain

    @staticmethod
    def _parse_cookies(cookie_str: str) -> dict[str, str]:
        return dict(item.split("=", 1) for item in cookie_str.split("; ") if "=" in item)

    async def listen(self, watch_chats: list[str] | None = None) -> AsyncGenerator[dict, None]:
        """Connect to WebSocket and yield Message dicts."""
        async for msg in listener.listen(self._cookie, self._cookies, watch_chats, self._domain):
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
        """Search message IDs with auto-pagination. Returns {"msg_ids": [...], "has_more": bool}."""
        return await search.search_msg_ids(
            self._cookie, chat_id, start_time, end_time, from_id, mention_user_id, limit, self._domain
        )

    async def search_messages_page(
        self,
        chat_id: str,
        start_time: int = 0,
        end_time: int = 0,
        from_id: str = "",
        mention_user_id: str = "",
        page_token: str = "",
    ) -> dict:
        """Search message IDs - single page.

        Returns {"msg_ids": [...], "has_more": bool, "page_token": str}.
        Pass returned page_token to next call to paginate.
        """
        return await search.search_msg_ids_page(
            self._cookie, chat_id, start_time, end_time, from_id, mention_user_id, page_token, self._domain
        )

    async def fetch_messages(self, msg_ids: list[str]) -> list[dict]:
        """Fetch message content by IDs."""
        return await search.fetch_messages(self._cookie, msg_ids, self._domain)

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_id: str = "",
        at_user_ids: list[str] | None = None,
    ) -> bool:
        """Send a text message. Returns True on success."""
        return await sender.send_message(self._cookie, chat_id, text, reply_id, at_user_ids, self._domain)

    async def create_folder(self, name: str, parent_token: str = "") -> dict | None:
        """Create a Drive folder. Returns {"token", "url"} or None."""
        return await drive.create_folder(self._cookie, self._cookies, name, parent_token, self._domain)

    async def upload_file(self, folder_token: str, file_name: str, file_content: bytes) -> dict | None:
        """Upload a file to Drive. Returns {"file_token", "node_token"} or None."""
        return await drive.upload_file(self._cookie, self._cookies, folder_token, file_name, file_content, self._domain)

    async def export_document(self, token: str, type: str, file_extension: str) -> bytes | None:
        """Export a document. Returns file bytes or None.

        Args:
            token: Document token (obj_token). For wiki pages, call resolve_wiki_token first.
            type: Document type - "docx" (wiki/docx pages), "sheet".
            file_extension: Export format.
                - docx → "markdown", "docx", "pdf"
                - sheet → "xlsx" only
        """
        return await drive.export_document(self._cookie, self._cookies, token, type, file_extension, self._domain)

    async def resolve_wiki_token(self, wiki_token: str) -> tuple[str, str]:
        """Resolve a wiki_token to (obj_token, type). Returns ("", "") on failure."""
        return await drive._resolve_wiki_token(self._cookie, self._cookies, wiki_token, self._domain)

    async def download_file(self, file_token: str) -> bytes | None:
        """Download a file from Drive. Returns file bytes or None."""
        return await drive.download_file(self._cookie, self._cookies, file_token, self._domain)

    async def import_document(
        self,
        folder_token: str,
        file_name: str,
        file_content: bytes,
        file_extension: str = "md",
        target_type: str = "docx",
    ) -> dict | None:
        """Import a file (e.g. markdown) as an online document.

        Args:
            folder_token: Target folder token.
            file_name: File name (e.g. "report.md").
            file_content: Raw file bytes.
            file_extension: Source format - "md", "docx", "xlsx".
            target_type: Target doc type - "docx", "sheet".

        Returns {"token", "url"} or None.
        """
        return await drive.import_document(
            self._cookie,
            self._cookies,
            folder_token,
            file_name,
            file_content,
            file_extension,
            target_type,
            self._domain,
        )

    async def list_my_space(self) -> list[dict]:
        """List root folders in 'My Space'."""
        return await drive.list_my_space(self._cookie, self._cookies, self._domain)

    async def list_shared_folders(self) -> list[dict]:
        """List root folders in 'Shared Space'."""
        return await drive.list_shared_folders(self._cookie, self._cookies, self._domain)

    async def list_children(self, folder_token: str) -> list[dict]:
        """List children (files + subfolders) of a folder."""
        return await drive.list_children(self._cookie, self._cookies, folder_token, self._domain)

    async def delete_nodes(self, tokens: list[str]) -> bool:
        """Delete files/folders by node tokens. Returns True on success."""
        return await drive.delete_nodes(self._cookie, self._cookies, tokens, self._domain)
