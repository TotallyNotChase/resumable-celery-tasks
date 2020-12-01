from typing import Any, Optional

from celery import shared_task
from celery.canvas import Signature, chain, signature

@shared_task(bind=True)
def cancel(self, retval: Optional[Any]=None, clause: Signature=None):
    if signature(clause)(retval,):
        self.request.chain = None
    return retval

def tappable(ch: chain, clause: Signature, nth: Optional[int]=1):
    newch = []
    for n, sig in enumerate(ch.tasks):
        if n != 0 and n % nth == nth - 1:
            newch.append(cancel.s(clause=clause))
        newch.append(sig)
    ch.tasks = tuple(newch)
    return ch
