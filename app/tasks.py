import time
import json

from app import celery

@celery.task()
def add(a: int, b: int):
    time.sleep(5)
    return a + b

@celery.task()
def mult(a: int, b: int):
    time.sleep(5)
    return a * b

@celery.task()
def check(_):
    return True

@celery.task()
def save_state(retval, chains):
    with open('chains.json', 'w') as f:
        json.dump(chains, f)
