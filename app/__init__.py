from flask import Flask

from app.celery import make_celery

app = Flask(__name__)
app.config.from_object('app.config')
celery = make_celery(app)
celery.autodiscover_tasks(related_name='tappable')

from app import views
