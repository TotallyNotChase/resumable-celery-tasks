import time

from celery import Task

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
    return False
