from typing import List

from celery.canvas import signature, chain

def deserialize_chain(serialized_ch: List[dict]):
    return chain(signature(x) for x in serialized_ch)
