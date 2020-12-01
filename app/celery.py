from flask import Flask
from celery import Celery, Task

def make_celery(app: Flask):
    celery = Celery(
        app.import_name,
    )
    celery.config_from_object(app.config, namespace='CELERY')

    class ContextTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
