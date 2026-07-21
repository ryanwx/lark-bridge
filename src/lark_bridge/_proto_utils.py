"""Protobuf → dict conversion utilities.

Replaces the deprecated protobuf3-to-dict library with google.protobuf.json_format.MessageToDict,
with adjustments to match the old library's behavior.
"""

import base64

from google.protobuf.json_format import MessageToDict as _MessageToDict


def proto_to_dict(message) -> dict:
    """Convert a protobuf message to a Python dict.

    Matches the behavior of the old protobuf3-to-dict library:
    - Enums are kept as integers
    - bytes fields are restored from base64 to actual bytes
    - Only fields with non-default values are included
    """
    d = _MessageToDict(
        message,
        use_integers_for_enums=True,
        preserving_proto_field_name=True,
    )
    _restore_bytes_fields(d, message)
    return d


def _restore_bytes_fields(d: dict, message) -> None:
    """Recursively restore bytes fields from base64 strings back to bytes.

    MessageToDict encodes bytes as base64 strings. The old protobuf_to_dict
    returned them as raw bytes. We restore that behavior for compatibility.
    """
    descriptor = message.DESCRIPTOR
    for field in descriptor.fields:
        if field.name not in d:
            continue

        if field.type == field.TYPE_BYTES:
            val = d[field.name]
            if isinstance(val, str):
                try:
                    d[field.name] = base64.b64decode(val)
                except Exception:
                    pass
            elif isinstance(val, list):
                d[field.name] = [base64.b64decode(v) if isinstance(v, str) else v for v in val]

        elif field.type == field.TYPE_MESSAGE:
            if field.label == field.LABEL_REPEATED:
                if field.message_type.GetOptions().map_entry:
                    # Map field — check value type
                    value_field = field.message_type.fields_by_name["value"]
                    if value_field.type == value_field.TYPE_BYTES:
                        map_dict = d[field.name]
                        if isinstance(map_dict, dict):
                            for k, v in map_dict.items():
                                if isinstance(v, str):
                                    try:
                                        map_dict[k] = base64.b64decode(v)
                                    except Exception:
                                        pass
                    elif value_field.type == value_field.TYPE_MESSAGE:
                        map_dict = d[field.name]
                        if isinstance(map_dict, dict):
                            map_obj = getattr(message, field.name)
                            for k, v in map_dict.items():
                                if isinstance(v, dict) and k in map_obj:
                                    _restore_bytes_fields(v, map_obj[k])
                else:
                    # Repeated message
                    items = d[field.name]
                    repeated_obj = getattr(message, field.name)
                    for i, item in enumerate(items):
                        if isinstance(item, dict) and i < len(repeated_obj):
                            _restore_bytes_fields(item, repeated_obj[i])

            else:
                # Singular message
                sub_dict = d[field.name]
                if isinstance(sub_dict, dict):
                    sub_msg = getattr(message, field.name)
                    _restore_bytes_fields(sub_dict, sub_msg)
