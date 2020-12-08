# Celery config keys

# Make celery propagate exceptions instead of retrying
CELERY_TASK_EAGER_PROPAGATES = True
# Set expiry on task results (in seconds)
CELERY_RESULT_EXPIRES = 5
# Set the `backend_cleanup` task to run every 5 minutes
CELERY_BEAT_SCHEDULE = {
    "backend_cleanup": {
        "task": "celery.backend_cleanup",
        "schedule": 5.0 * 60.0,
    },
}
# Route the backend_cleanup task to a separate queue
CELERY_TASK_ROUTES = {"celery.backend_cleanup": {"queue": "periodic_cleanup"}}
