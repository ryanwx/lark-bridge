"""Search and fetch messages from Feishu internal API."""

import hashlib
import json
import time

import httpx

from google.protobuf.internal.decoder import _DecodeVarint
from protobuf_to_dict import protobuf_to_dict

from lark_bridge.proto import proto_pb2 as pb
from lark_bridge.decoder import decode_text

GATEWAY_URL = "https://internal-api-lark-api.feishu.cn/im/gateway/"


def _ev(v: int) -> bytes:
    """Encode int as protobuf varint."""
    p = []
    while v > 0x7F:
        p.append((v & 0x7F) | 0x80)
        v >>= 7
    p.append(v & 0x7F)
    return bytes(p)


def _headers(cookie: str, xcmd: int, rid: str) -> dict:
    return {
        "Cookie": cookie,
        "content-type": "application/x-protobuf",
        "locale": "en-US",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-command": str(xcmd),
        "x-command-version": "7.68.5",
        "x-appid": "161471",
        "x-lgw-os-type": "1",
        "x-lgw-req-sdk-type": "220",
        "x-lgw-terminal-type": "2",
        "x-lsc-bizid": "1",
        "x-lsc-version": "1",
        "x-request-id": rid,
        "x-source": "web",
        "x-web-version": "7.68.5",
        "origin": "https://www.feishu.cn",
        "referer": "https://www.feishu.cn/",
    }


def _build_search_params(chat_id: str, start_time: int, end_time: int, from_id: str, mention_user_id: str) -> bytes:
    """Build the search_params protobuf portion."""
    chat_filter = b"\x08\x01\x12" + bytes([len(chat_id)]) + chat_id.encode()

    field3_content = b""
    if start_time and end_time:
        time_range = b"\x08" + _ev(start_time) + b"\x10" + _ev(end_time)
        field3_content += b"\x0a" + _ev(len(time_range)) + time_range
    if from_id:
        field3_content += b"\x12" + bytes([len(from_id)]) + from_id.encode()
    if mention_user_id:
        field3_content += b"\x32" + bytes([len(mention_user_id)]) + mention_user_id.encode()
    field3_content += b"\x1a\x06\x2a\x04\x08\x01\x28\x01"

    if field3_content:
        time_outer = b"\x1a" + _ev(len(field3_content)) + field3_content
        filter_field2 = b"\x12" + _ev(len(time_outer)) + time_outer
        search_filter = b"\x08\x05" + filter_field2
    else:
        search_filter = b"\x08\x05\x1a\x04\x2a\x02\x28\x01"

    search_params = b"\x0a\x0fSEARCH_MESSAGES"
    search_params += b"\x12" + _ev(len(search_filter)) + search_filter
    search_params += b"\x1a" + _ev(len(chat_filter)) + chat_filter
    return search_params


async def search_msg_ids(
    cookie: str,
    chat_id: str,
    start_time: int = 0,
    end_time: int = 0,
    from_id: str = "",
    mention_user_id: str = "",
    limit: int = 15,
) -> dict:
    """Search message IDs by chat_id and time range (unix seconds).

    Returns dict: {"msg_ids": [...], "has_more": bool}
    """
    session_id = hashlib.md5(f"{time.time()}".encode()).hexdigest()[:10]
    search_params = _build_search_params(chat_id, start_time, end_time, from_id, mention_user_id)

    all_msg_ids: list[str] = []
    page_token_str = ""
    has_more = False

    async with httpx.AsyncClient(verify=False, timeout=15) as client:
        while len(all_msg_ids) < limit:
            page_token_bytes = page_token_str.encode() if page_token_str else b""

            search_req = b"\x0a" + bytes([len(session_id)]) + session_id.encode()
            search_req += b"\x10\x01\x1a\x00"
            if page_token_bytes:
                search_req += b"\x22" + _ev(len(page_token_bytes)) + page_token_bytes
            search_req += b"\x2a" + _ev(len(search_params)) + search_params
            search_req += b"\x32\x05en_US"

            inner = b"\x0a" + _ev(len(search_req)) + search_req

            rid = hashlib.md5(f"{time.time()}{len(all_msg_ids)}".encode()).hexdigest()[:10]
            pkt = pb.Packet()
            pkt.payloadType = 1
            pkt.cmd = 11021
            pkt.payload = inner
            pkt.cid = rid

            resp = await client.post(
                GATEWAY_URL,
                headers=_headers(cookie, 11021, rid),
                content=pkt.SerializeToString(),
            )
            if resp.status_code != 200:
                break

            rpkt = pb.Packet()
            rpkt.ParseFromString(resp.content)
            pl = protobuf_to_dict(rpkt).get("payload", b"")
            if not pl:
                break

            msg_ids: list[str] = []
            json_str = ""
            pos2 = 0
            while pos2 < len(pl):
                try:
                    tag, new_pos = _DecodeVarint(pl, pos2)
                    fn, wt = tag >> 3, tag & 7
                    if wt == 2:
                        ln, new_pos = _DecodeVarint(pl, new_pos)
                        val = pl[new_pos : new_pos + ln]
                        if fn == 1:
                            val_text = val.decode("utf-8", errors="replace")
                            jj = val_text.find("{")
                            if jj >= 0:
                                json_str = val_text[jj : val_text.rfind("}") + 1]
                        elif fn == 2:
                            if len(val) > 21 and val[0:2] == b"\x0a\x13":
                                mid = val[2:21].decode("utf-8", errors="replace")
                                if mid.startswith("7") and mid.isdigit():
                                    msg_ids.append(mid)
                        pos2 = new_pos + ln
                    elif wt == 0:
                        _, pos2 = _DecodeVarint(pl, new_pos)
                    else:
                        break
                except Exception:
                    break

            if not msg_ids:
                break
            all_msg_ids.extend(msg_ids)

            if not json_str:
                break
            try:
                j = json.loads(json_str)
                has_more = bool(j.get("HasMore"))
                if not has_more:
                    break
                page_token_str = json.dumps(j, separators=(",", ":"))
            except Exception:
                break

    all_msg_ids = list(dict.fromkeys(all_msg_ids))[:limit]
    return {"msg_ids": all_msg_ids, "has_more": has_more or len(all_msg_ids) >= limit}


async def fetch_messages(cookie: str, msg_ids: list[str]) -> list[dict]:
    """Fetch message content by msg_ids. Returns list of message dicts."""
    if not msg_ids:
        return []

    inner = b""
    for mid in msg_ids:
        inner += b"\x0a" + bytes([len(mid)]) + mid.encode()

    rid = hashlib.md5(f"{time.time()}fetch".encode()).hexdigest()[:10]
    pkt = pb.Packet()
    pkt.payloadType = 1
    pkt.cmd = 8
    pkt.payload = inner
    pkt.cid = rid

    async with httpx.AsyncClient(verify=False, timeout=15) as client:
        resp = await client.post(
            GATEWAY_URL,
            headers=_headers(cookie, 8, rid),
            content=pkt.SerializeToString(),
        )

    if resp.status_code != 200 or len(resp.content) < 50:
        return []

    rpkt = pb.Packet()
    rpkt.ParseFromString(resp.content)
    pl = protobuf_to_dict(rpkt).get("payload", b"")
    if not pl:
        return []

    try:
        push = pb.PushMessagesRequest()
        push.ParseFromString(pl)
        messages_raw = protobuf_to_dict(push).get("messages", {})
    except Exception:
        return []

    results = []
    for mid, m in messages_raw.items():
        results.append(
            {
                "msg_id": mid,
                "type": m.get("type", 0),
                "from_id": m.get("fromId", ""),
                "chat_id": m.get("chatId", ""),
                "create_time": m.get("createTime", 0),
                "text": decode_text(m),
            }
        )
    return results
