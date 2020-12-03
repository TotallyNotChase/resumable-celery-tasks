from typing import Any, Optional

from celery import shared_task
from celery.canvas import Signature, chain, signature


@shared_task(bind=True)
def pause_or_continue(
    self, retval: Optional[Any] = None, clause: dict = None, callback: dict = None
):
    # Task to use for deciding whether to pause the operation chain
    if signature(clause)(retval):
        # Pause requested, call given callback with retval and remaining chain
        # chain should be reversed as the order of execution follows from end to start
        signature(callback)(retval, self.request.chain[::-1])
        self.request.chain = None
    else:
        # Continue to the next task in chain
        return retval


def tappable(ch: chain, clause: Signature, callback: Signature, nth: Optional[int] = 1):
    '''
    Make a operation workflow chain pause-able/resume-able by inserting
    the pause_or_continue task for every nth task in given chain

    ch: chain
        The workflow chain

    clause: Signature
        Signature of a task that takes one argument - return value of
        last executed task in workflow (if any - othewise `None` is passsed)
        - and returns a boolean, indicating whether or not the operation should continue

        Should return True if operation should continue normally, or be paused

    callback: Signature
        Signature of a task that takes 2 arguments - return value of
        last executed task in workflow (if any - othewise `None` is passsed) and
        remaining chain of the operation workflow as a json dict object
        No return value is expected

        This task will be called when `clause` returns `True` (i.e task is pausing)
        The return value and the remaining chain can be handled accordingly by this task

    nth: Int
        Check `clause` after every nth task in the chain
        Default value is 1, i.e check `clause` after every task
        Hence, by default, user given `clause` is called and checked
        after every task

    NOTE: The passed in chain is mutated in place
    Returns the mutated chain
    '''
    newch = []
    for n, sig in enumerate(ch.tasks):
        if n != 0 and n % nth == nth - 1:
            newch.append(pause_or_continue.s(clause=clause, callback=callback))
        newch.append(sig)
    ch.tasks = tuple(newch)
    return ch
