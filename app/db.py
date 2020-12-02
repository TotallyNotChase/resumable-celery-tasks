import os
import sqlite3

import click
from flask import current_app
from flask import g
from flask.app import Flask
from flask.cli import with_appcontext


def get_db():
    # Connect to the database / return existing connection
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row

    return g.db


def close_db(e=None):
    # Close db connection if existing
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    # Clear existing data and create new tables
    db = get_db()

    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))


@click.command("init-db")
@with_appcontext
def init_db_command():
    # Clear existing data and create new tables
    init_db()
    click.echo("Initialized the database")


def init_app(app: Flask):
    # Register database functions with the Flask app
    if not os.path.isdir(app.instance_path):
        # Create the instance directory if it doesn't exist already
        os.mkdir(app.instance_path)
    db_path = os.path.dirname(app.config["DATABASE"])
    if not os.path.isdir(db_path):
        # Create the db directory if it doesn't exist already
        os.mkdir(db_path)
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
