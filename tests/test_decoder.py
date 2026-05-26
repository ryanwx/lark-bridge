from lark_bridge.decoder import decode_text, decode_type4


def test_decode_empty():
    assert decode_text({"type": 4, "content": b""}) == ""
    assert decode_text({"type": 4, "content": None}) == ""
    assert decode_text({}) == ""


def test_decode_type4():
    # Empty bytes should not crash
    assert decode_type4(b"") == ""
    # Invalid protobuf should return empty string gracefully
    assert decode_type4(b"\x00\x01\x02") == ""
