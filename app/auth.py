import functools
from typing import Optional

from flask import flash, redirect, render_template, url_for
from flask.globals import g, request, session
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash

from app import app
from app.db import get_db


def login_required(view):
    # View decorator to redirect non-logged users to login page

    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("login"))

        return view(**kwargs)

    return wrapped_view


@app.before_request
def load_logged_in_user():
    # Load logged in user from session, if present
    user_id: Optional[int] = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        g.user = (
            get_db().execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        )


@app.route("/signup", methods=("GET", "POST"))
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        db = get_db()

        # Error checking the form inputs
        error = None
        if not username:
            error = "Username is required"
        elif not password:
            error = "Password is required"
        elif (
            db.execute("SELECT id FROM user WHERE username = ?", (username,)).fetchone()
            is not None
        ):
            error = f"An account with the username '{username}' already exists"

        if error is None:
            # Store the user into the database and get the id (aka last inserted row id in this connection)
            user_id: int = db.execute(
                "INSERT INTO user (username, password) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            ).lastrowid

            # Assign user id to session
            session.clear()
            session["user_id"] = user_id

            # Commit the transaction
            db.commit()
            return redirect(url_for("index"))

        # Flash error if there was one
        flash(error)

    return render_template("auth/signup.html")


@app.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        db = get_db()

        # Error checking the form inputs
        error = None
        # Fetch the user object for verification
        user = db.execute(
            "SELECT * FROM user WHERE username = ?", (username,)
        ).fetchone()
        if user is None:
            error = "Incorrect username"
        elif not check_password_hash(user["password"], password):
            error = "Incorrect password"

        if error is None:
            # Assign user id to session
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("index"))

        # Flash error if there was one
        flash(error)

    return render_template("auth/login.html")


@app.route("/logout")
def logout():
    # Logout route - clears session
    session.clear()
    return redirect(url_for("index"))
