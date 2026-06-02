"""Feishu WebSocket listener - yields Message dicts."""

import asyncio
import hashlib
import logging
import re
import time
from collections.abc import AsyncGenerator
from typing import TypedDict
from urllib.parse import urlencode

import httpx
import websockets

from lark_bridge.proto import proto_pb2 as pb
from lark_bridge.decoder import decode_text
from protobuf_to_dict import protobuf_to_dict

logger = logging.getLogger(__name__)

INTERNAL_API = "https://internal-api-lark-api.feishu.cn"


class Message(TypedDict):
    msg_id: str
    chat_id: str
    from_id: str
    type: int
    chat_type: int
    text: str
    parent_id: str
    root_id: str
    create_time: int


async def listen(
    cookie: str,
    cookies: dict[str, str],
    watch_chats: list[str] | None = None,
    domain: str = "",
) -> AsyncGenerator[Message, None]:
    """Connect to Feishu WebSocket and yield Message dicts.

    Reconnects automatically on disconnect.
    """
    while True:
        try:
            params = await build_ws_params(cookie, cookies, domain)
            if not params:
                logger.error("Failed to build WS params, retrying in 30s")
                await asyncio.sleep(30)
                continue

            url = f"wss://msg-frontier.feishu.cn/ws/v2?{urlencode(params)}"
            logger.info("Connecting to Feishu WebSocket...")

            async with websockets.connect(url) as ws:
                logger.info("WebSocket connected")
                async for data in ws:
                    try:
                        sid, msgs = _handle_frame(data, watch_chats)
                        if sid:
                            await ws.send(_build_ack(sid))
                        for msg in msgs:
                            yield msg
                    except Exception as e:
                        logger.debug(f"Frame error: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"WebSocket disconnected: {e}, reconnecting in 5s")
            await asyncio.sleep(5)


def _handle_frame(data: bytes, watch_chats: list[str] | None) -> tuple[int, list[Message]]:
    """Decode a WebSocket frame. Returns (sid, list of Message dicts)."""
    frame = pb.Frame()
    frame.ParseFromString(data)
    frame_dict = protobuf_to_dict(frame)

    payload = frame_dict.get("payload")
    if not payload:
        return 0, []

    packet = pb.Packet()
    packet.ParseFromString(payload)
    packet_dict = protobuf_to_dict(packet)
    sid = packet_dict.get("sid", 0)

    if packet_dict.get("cmd") != 6:
        return sid, []

    inner = packet_dict.get("payload")
    if not inner:
        return sid, []

    try:
        push = pb.PushMessagesRequest()
        push.ParseFromString(inner)
        push_dict = protobuf_to_dict(push)
    except Exception:
        return sid, []

    messages: list[Message] = []
    for msg_id, msg in push_dict.get("messages", {}).items():
        chat_id = msg.get("chatId", "")
        if watch_chats and chat_id not in watch_chats:
            continue
        messages.append(
            Message(
                msg_id=msg_id,
                chat_id=chat_id,
                from_id=msg.get("fromId", ""),
                type=msg.get("type", 0),
                chat_type=msg.get("chatType", 0),
                text=decode_text(msg),
                parent_id=msg.get("parentId", ""),
                root_id=msg.get("rootId", ""),
                create_time=msg.get("createTime", 0),
            )
        )

    return sid, messages


def _build_ack(sid: int) -> bytes:
    """Build ACK packet for a given sid."""
    if not sid:
        return b""
    packet = pb.Packet()
    packet.cmd = 1
    packet.payloadType = 1
    packet.sid = sid

    frame = pb.Frame()
    now_ms = int(time.time() * 1000)
    frame.seqid = now_ms
    frame.logid = now_ms
    frame.service = 1
    frame.method = 1
    frame.payloadType = "pb"
    frame.payload = packet.SerializeToString()

    entry = pb.ExtendedEntry()
    entry.key = "x-request-time"
    entry.value = f"{now_ms}000"
    frame.headers.append(entry)

    return frame.SerializeToString()


async def build_ws_params(cookie: str, cookies: dict[str, str], domain: str = "") -> dict | None:
    """Build WebSocket connection parameters."""
    try:
        device_id = cookies.get("passport_web_did", "")
        if not device_id:
            logger.error("No passport_web_did in cookies")
            return None

        headers = {
            "Cookie": cookie,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        async with httpx.AsyncClient(headers=headers, verify=False, timeout=15) as client:
            # Get appKey
            app_key = None
            resp = await client.get(f"https://{domain}/messenger/", follow_redirects=True)
            match = re.search(r"appKey:\s*[\"']([^\"']+)[\"']", resp.text)
            if match:
                app_key = match.group(1)
            else:
                js_matches = re.findall(r'src="(https://[^"]+/lark\.[^"]+\.js)"', resp.text)
                for js_url in js_matches:
                    js_resp = await client.get(js_url)
                    m = re.search(r'sass\s*:\s*"([a-f0-9]+)"', js_resp.text)
                    if m:
                        app_key = m.group(1)
                        break
            if not app_key:
                logger.error("Cannot find appKey")
                return None

            access_key = hashlib.md5(f"2{app_key}{device_id}f8a69f1719916z".encode()).hexdigest()

            # Get ticket
            resp = await client.get(
                "https://login.feishu.cn/suite/passport/frontier_ticket/",
                params={"local_device_id": device_id},
            )
            ticket = resp.json().get("ticket", "")

            return {
                "access_key": access_key,
                "aid": "1",
                "ticket": ticket,
                "device_id": device_id,
                "fpid": "2",
                "accept_encoding": "gzip",
                "request_id": hashlib.md5(str(time.time()).encode()).hexdigest()[:10],
            }
    except Exception as e:
        logger.error(f"Build WS params failed: {e}")
        return None
