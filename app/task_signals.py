from celery.signals import task_success

from app.tasks import gamer

@task_success.connect
def launch_next(result, **kwargs):
    gamer.delay(result)
