# lark-bridge

Unofficial Feishu/Lark Web SDK using cookie-based authentication. Provides real-time message listening via WebSocket, message search/fetch, sending, and Drive operations.

> ⚠️ This library is reverse-engineered from Feishu's web client. It is **not** an official API and may break without notice.

## Installation

```bash
pip install lark-bridge
```

## Quick Start

```python
import asyncio
from lark_bridge import LarkBridge

bridge = LarkBridge("your_cookie_string_here")

# For enterprise tenants with custom domain:
bridge = LarkBridge("your_cookie_string_here", domain="yourcompany.feishu.cn")
```

### Listen to Messages

```python
async def main():
    async for msg in bridge.listen(watch_chats=["chat_id"]):
        print(f"[{msg['chat_id']}] {msg['from_id']}: {msg['text']}")

asyncio.run(main())
```

### Search History

```python
# Simple: auto-paginate up to limit
result = await bridge.search_messages(
    chat_id="7052636707732193282",
    start_time=1716192000,
    end_time=1716278400,
    limit=50,
)
print(result["msg_ids"])

# Manual pagination:
page = await bridge.search_messages_page(chat_id="7052636707732193282")
while page["has_more"]:
    page = await bridge.search_messages_page(
        chat_id="7052636707732193282",
        page_token=page["page_token"],
    )
    print(page["msg_ids"])
```

### Fetch Messages

```python
messages = await bridge.fetch_messages(["msg_id_1", "msg_id_2"])
for msg in messages:
    print(msg["text"])
```

### Send Message

```python
await bridge.send_message(
    chat_id="7052636707732193282",
    text="Hello!",
    reply_id="optional_msg_id",
    at_user_ids=["user_id"],
)
```

### Drive Operations

```python
folder = await bridge.create_folder("My Folder", parent_token="root_token")
# folder = {"token": "...", "url": "https://domain/drive/folder/..."}

result = await bridge.upload_file(folder["token"], "report.txt", b"file content")
# result = {"file_token": "...", "node_token": "...", "url": "https://domain/file/..."}
```

## Cookie Setup

1. Open [Feishu Web](https://www.feishu.cn/) in your browser and log in
2. Open DevTools (F12) → Application → Cookies
3. Copy the full cookie string (all key=value pairs joined by `; `)
4. Pass it to `LarkBridge("your_cookie_string")`

Example cookie format:

```python
cookie = "passport_web_did=YOUR_DID; session=YOUR_SESSION; _csrf_token=YOUR_CSRF_TOKEN"

bridge = LarkBridge(cookie)
```

Cookie typically stays valid as long as the WebSocket connection is maintained.

## License

[MIT](LICENSE)
