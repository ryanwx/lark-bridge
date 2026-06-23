"""MCP Server for lark-bridge.

Usage:
    FEISHU_COOKIE="..." lark-bridge-mcp

    # For enterprise tenants with custom domain:
    FEISHU_COOKIE="..." FEISHU_DOMAIN="yourcompany.feishu.cn" lark-bridge-mcp
"""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from lark_bridge import LarkBridge

mcp = FastMCP("lark-bridge")


def _get_bridge() -> LarkBridge:
    cookie_file = os.environ.get("FEISHU_COOKIE_FILE")
    if cookie_file:
        cookie = Path(cookie_file).read_text().strip()
    else:
        cookie = os.environ["FEISHU_COOKIE"]
    return LarkBridge(cookie, os.environ.get("FEISHU_DOMAIN", "www.feishu.cn"))


@mcp.tool()
async def send_message(chat_id: str, text: str, reply_id: str = "", at_user_ids: list[str] | None = None) -> str:
    """发送飞书消息到指定会话"""
    ok = await _get_bridge().send_message(chat_id, text, reply_id, at_user_ids)
    return "sent" if ok else "failed"


@mcp.tool()
async def search_messages(
    chat_id: str, start_time: int = 0, end_time: int = 0, from_id: str = "", mention_user_id: str = "", limit: int = 50
) -> list[str]:
    """搜索飞书消息ID，支持按时间、发送者、@用户筛选"""
    result = await _get_bridge().search_messages(chat_id, start_time, end_time, from_id, mention_user_id, limit)
    return result["msg_ids"]


@mcp.tool()
async def fetch_messages(msg_ids: list[str]) -> list[dict]:
    """获取消息详情。返回 msg_id, type, from_id, chat_id, chat_type, text, create_time 等字段"""
    return await _get_bridge().fetch_messages(msg_ids)


@mcp.tool()
async def create_folder(name: str, parent_token: str = "") -> dict | None:
    """在飞书云文档创建文件夹。返回 {"token": "...", "url": "..."}"""
    return await _get_bridge().create_folder(name, parent_token)


@mcp.tool()
async def upload_file(folder_token: str, file_name: str, file_content_base64: str) -> dict | None:
    """上传文件到飞书云文档。file_content_base64 为 base64 编码的文件内容。返回 {"file_token", "node_token", "url"}"""
    import base64

    content = base64.b64decode(file_content_base64)
    return await _get_bridge().upload_file(folder_token, file_name, content)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
