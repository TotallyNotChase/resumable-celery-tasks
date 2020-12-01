import os
# Config file for flask app

# Celery config keys
CELERY_broker_url = os.environ['CELERY_BROKER_URL']
CELERY_result_backend = os.environ['CELERY_RESULT_BACKEND']
# Make celery propagate exceptions instead of retrying
CELERY_task_eager_propagates = True

# 'amqp://atlanuser:atlanpass@localhost:5672/atlanvhost'