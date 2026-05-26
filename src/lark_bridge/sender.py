"""Send messages via Feishu internal gateway."""

import hashlib
import logging
import time

import httpx

from lark_bridge.proto import proto_pb2 as pb

logger = logging.getLogger(__name__)

GATEWAY_URL = "https://internal-api-lark-api.feishu.cn/im/gateway/"


def _build_send_packet(
    text: str,
    chat_id: str,
    reply_id: str = "",
    at_user_ids: list[str] | None = None,
) -> tuple[bytes, str]:
    """Build protobuf packet for sending a message."""
    request_id = hashlib.md5(f"{time.time()}{id(object())}".encode()).hexdigest()[:10]

    packet = pb.Packet()
    packet.payloadType = 1
    packet.cmd = 5
    packet.cid = request_id

    msg = pb.PutMessageRequest()
    msg.type = 4
    msg.chatId = chat_id
    msg.cid = hashlib.md5(str(time.time()).encode()).hexdigest()[:10]
    msg.isNotified = 1
    msg.version = 1

    if reply_id:
        msg.parentId = reply_id
        msg.rootId = reply_id

    full_text = ""
    element_ids: list[str] = []

    for uid in at_user_ids or []:
        at_eid = hashlib.md5(f"a{uid}{time.time()}".encode()).hexdigest()[:10]
        at_tp = pb.TextProperty()
        at_tp.content = uid
        at_tp.i18nKey = f"@{uid}"
        msg.content.richText.elements.dictionary[at_eid].tag = 5
        msg.content.richText.elements.dictionary[at_eid].property = at_tp.SerializeToString()
        element_ids.append(at_eid)
        full_text += f"@{uid} "

    text_eid = hashlib.md5(f"t{time.time()}".encode()).hexdigest()[:10]
    tp = pb.TextProperty()
    tp.content = text
    msg.content.richText.elements.dictionary[text_eid].tag = 1
    msg.content.richText.elements.dictionary[text_eid].property = tp.SerializeToString()
    element_ids.append(text_eid)
    full_text += text

    msg.content.richText.innerText = full_text
    msg.content.richText.elementIds.extend(element_ids)
    if at_user_ids:
        for eid in element_ids[:-1]:
            msg.content.richText.atIds.append(eid)

    packet.payload = msg.SerializeToString()
    return packet.SerializeToString(), request_id


async def send_message(
    cookie: str,
    chat_id: str,
    text: str,
    reply_id: str = "",
    at_user_ids: list[str] | None = None,
) -> bool:
    """Send a text message. Returns True on success."""
    try:
        data, request_id = _build_send_packet(text, chat_id, reply_id, at_user_ids)
        headers = {
            "Cookie": cookie,
            "content-type": "application/x-protobuf",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-command": "5",
            "x-command-version": "5.7.0",
            "x-request-id": request_id,
            "x-appid": "161471",
            "x-source": "web",
            "x-web-version": "3.9.32",
            "x-lgw-os-type": "1",
            "x-lgw-terminal-type": "2",
            "origin": "https://open-dev.feishu.cn",
            "referer": "https://open-dev.feishu.cn/",
        }
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            resp = await client.post(GATEWAY_URL, headers=headers, content=data)
            if resp.status_code == 200:
                logger.info(f"Message sent to {chat_id}")
                return True
            logger.error(f"Send failed: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"Send error: {e}")
        return False
