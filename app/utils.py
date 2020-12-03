from base64 import b64encode, b64decode
from typing import List

from celery.canvas import signature, chain


def b64encode_id(_id: int):
    # Encode an int id to base64 string
    return b64encode(str(_id).encode("utf-8")).decode("utf-8")


def b64decode_id(b64_id: str):
    # Decode a base64 string to int id
    return int(b64decode(b64_id).decode("utf-8"))


def deserialize_chain(serialized_ch: List[dict]):
    # Build task signatures from list of dicts (serialized json)
    return chain(signature(x) for x in serialized_ch)
