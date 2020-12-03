import os

from flask import Flask
from flask.templating import render_template

from app.celery import make_celery

app = Flask(__name__)
app.config.from_mapping(
    # Do not use this secret key in production
    SECRET_KEY="very-super-secret",
    # Path to database
    DATABASE=os.path.join(app.instance_path, "db", "resumable.sqlite"),
    # Path to folder for storing operation info
    OPERATIONS=os.path.join(app.instance_path, "operations"),
)
app.config.from_object("app.config")

celery = make_celery(app)
celery.autodiscover_tasks(related_name="tappable")


@app.route("/")
def index():
    return render_template("base.html")


from app import db

db.init_app(app)

from app import auth
from app import operations
