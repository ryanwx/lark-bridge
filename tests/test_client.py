import pytest
from unittest.mock import AsyncMock, patch

from lark_bridge.client import LarkBridge


def test_init():
    bridge = LarkBridge("session=abc123; uid=user1")
    assert bridge._cookie == "session=abc123; uid=user1"


def test_parse_cookies():
    bridge = LarkBridge("session=abc123; uid=user1; token=xyz")
    assert bridge._cookies == {"session": "abc123", "uid": "user1", "token": "xyz"}


@pytest.mark.asyncio
async def test_search_messages_no_cookie():
    bridge = LarkBridge("")
    with patch("lark_bridge.search.search_msg_ids", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = {"msg_ids": [], "has_more": False}
        result = await bridge.search_messages("chat_id_123", 0, 0)
        assert result == {"msg_ids": [], "has_more": False}
        mock_search.assert_called_once_with("", "chat_id_123", 0, 0, "", "", 15)
