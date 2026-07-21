"""Text decoding for Feishu message protobuf content."""

import json
import re

from google.protobuf.internal.decoder import _DecodeVarint

from lark_bridge.proto import proto_pb2 as pb
from lark_bridge._proto_utils import proto_to_dict


def decode_text(msg: dict) -> str:
    """Extract text from a message dict (with 'type' and 'content' fields)."""
    msg_type = msg.get("type", 0)
    content = msg.get("content", b"")
    if not content:
        return ""
    if msg_type == 4:
        return decode_type4(content)
    elif msg_type == 14:
        return decode_type14(content)
    return ""


def decode_type4(content: bytes) -> str:
    """Decode type=4 (plain text) message.

    Primary: extract field 1 directly from wire format (newer Feishu encoding).
    Fallback: parse as TextContent proto and walk richText tree (legacy encoding).
    """
    # Primary: wire format field 1 = text content (varint tag 0x0a = field 1, wire type 2)
    text = _extract_wire_field1(content)
    if text:
        return text

    # Fallback: legacy richText tree
    try:
        tc = pb.TextContent()
        tc.ParseFromString(content)
        tc_dict = proto_to_dict(tc)
        rt = tc_dict.get("richText", {})
        elements = rt.get("elements", {}).get("dictionary", {})
        element_ids = rt.get("elementIds", [])
        at_ids = set(rt.get("atIds", []))

        def _extract(eid: str) -> str:
            el = elements.get(eid, {})
            prop = el.get("property", b"")
            parts: list[str] = []
            if prop:
                tp = pb.TextProperty()
                tp.ParseFromString(prop)
                if eid in at_ids:
                    parts.append(f"@({tp.content})")
                elif tp.content:
                    parts.append(tp.content)
            for cid in el.get("childIds", []):
                parts.append(_extract(cid))
            return "".join(parts)

        result = "".join(_extract(eid) for eid in element_ids)
        if result:
            return result
    except Exception:
        pass

    return ""


def _extract_wire_field1(data: bytes) -> str:
    """Extract field 1 (wire type 2 = length-delimited) as UTF-8 string from raw protobuf bytes."""
    try:
        pos = 0
        while pos < len(data):
            tag, new_pos = _DecodeVarint(data, pos)
            fn = tag >> 3
            wt = tag & 0x7
            if wt == 2:  # length-delimited
                length, new_pos = _DecodeVarint(data, new_pos)
                val = data[new_pos : new_pos + length]
                if fn == 1:
                    text = val.decode("utf-8", errors="replace")
                    # Sanity check: should look like actual text, not a nested proto
                    if text and not text.startswith("\x08") and not text.startswith("\x0a"):
                        return text
                pos = new_pos + length
            elif wt == 0:  # varint
                _, pos = _DecodeVarint(data, new_pos)
            elif wt == 5:  # 32-bit
                pos = new_pos + 4
            elif wt == 1:  # 64-bit
                pos = new_pos + 8
            else:
                break
    except Exception:
        pass
    return ""


def decode_type14(content: bytes) -> str:
    """Decode type=14 (post/card) message."""
    try:
        title = ""
        json_body = ""
        pos = 0
        while pos < len(content):
            tag, new_pos = _DecodeVarint(content, pos)
            fn = tag >> 3
            wt = tag & 0x7
            if wt == 0:
                _, pos = _DecodeVarint(content, new_pos)
            elif wt == 2:
                length, pos = _DecodeVarint(content, new_pos)
                val = content[pos : pos + length]
                if fn == 20:
                    json_body = val.decode("utf-8", errors="replace")
                elif fn == 8:
                    try:
                        tp = 0
                        _, tp = _DecodeVarint(val, tp)
                        t_len, tp = _DecodeVarint(val, tp)
                        title = val[tp : tp + t_len].decode("utf-8", errors="replace")
                    except Exception:
                        pass
                pos += length
            else:
                break

        if json_body:
            body = json.loads(json_body)
            parts: list[str] = []
            for el in body.get("body", {}).get("elements", []):
                tag_name = el.get("tag", "")
                prop = el.get("property", {})
                if tag_name == "markdown":
                    for sub in prop.get("elements", []):
                        sub_tag = sub.get("tag", "")
                        sub_prop = sub.get("property", {})
                        if sub_tag == "plain_text":
                            parts.append(sub_prop.get("content", ""))
                        elif sub_tag == "br":
                            parts.append("\n")
                        elif sub_tag == "a":
                            parts.append(sub_prop.get("href", sub_prop.get("content", "")))
                        elif sub_tag == "at":
                            parts.append(f"@({sub_prop.get('userID', '')})")
                        else:
                            parts.append(sub_prop.get("content", ""))
                elif tag_name == "plain_text":
                    parts.append(prop.get("content", ""))
                elif tag_name == "br":
                    parts.append("\n")
            text = "".join(parts)
            if title:
                text = f"{title}\n{text}"
        else:
            # Fallback: protobuf tree traversal
            pos = 0
            _, pos = _DecodeVarint(content, pos)
            _, pos = _DecodeVarint(content, pos)
            _, pos = _DecodeVarint(content, pos)
            length, pos = _DecodeVarint(content, pos)
            rt = pb.RichText()
            rt.ParseFromString(content[pos : pos + length])
            rt_dict = proto_to_dict(rt)
            elems = rt_dict.get("elements", {}).get("dictionary", {})
            eids = rt_dict.get("elementIds", [])

            def _ext(eid: str) -> str:
                el = elems.get(eid, {})
                prop = el.get("property", b"")
                p: list[str] = []
                if prop:
                    tp = pb.TextProperty()
                    tp.ParseFromString(prop)
                    if tp.content:
                        p.append(tp.content)
                for cid in el.get("childIds", []):
                    p.append(_ext(cid))
                return "".join(p)

            text = "".join(_ext(eid) for eid in eids)
            if title:
                text = f"{title}\n{text}"

        return re.sub(r"\x1b\[[0-9;]*m", "", text)
    except Exception:
        return ""
