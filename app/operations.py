import json

from flask import render_template, redirect
from flask.globals import g
from flask.helpers import url_for

from app import app
from app.auth import login_required
from app.db import get_db
from app.tasks import add, mult, save_state, should_pause, completion
from app.tappable import tappable
from app.utils import deserialize_chain, b64encode_id, b64decode_id


@app.route("/operations")
@login_required
def operations_index():
    db = get_db()

    operation_ids = map(
        b64encode_id,
        (
            x["id"]
            for x in db.execute(
                "SELECT id FROM operations WHERE requester_id = ?", (g.user["id"],)
            ).fetchall()
        ),
    )

    operations = {i: url_for("operation_info", operation_id=i) for i in operation_ids}
    return render_template("operations/index.html", operations=operations)


@app.route("/operations/<operation_id>")
@login_required
def operation_info(operation_id):
    operation_id = b64decode_id(operation_id)
    db = get_db()

    operation = db.execute(
        "SELECT * FROM operations WHERE id = ?", (operation_id,)
    ).fetchone()

    return render_template(
        "operations/operation.html",
        operation_id=b64encode_id(operation_id),
        status=operation["completion"],
        result=operation["result"],
    )


@app.route("/operations/start", methods=("POST",))
@login_required
def start():
    db = get_db()
    operation_id: int = db.execute(
        "INSERT INTO operations (requester_id, completion) VALUES (?, ?)",
        (g.user["id"], "IN PROGRESS"),
    ).lastrowid
    tappable(
        (add.s(1, 2) | mult.s(4) | completion.s(operation_id)),
        should_pause.s(operation_id),
        save_state.s(operation_id),
    )()
    db.commit()
    return redirect(url_for("operation_info", operation_id=b64encode_id(operation_id)))


@app.route("/operations/pause/<operation_id>", methods=("POST",))
@login_required
def pause(operation_id):
    operation_id = b64decode_id(operation_id)
    db = get_db()

    operation = db.execute(
        "SELECT * FROM operations WHERE id = ?", (operation_id,)
    ).fetchone()

    if operation and operation["completion"] == "IN PROGRESS":
        db.execute(
            """
            UPDATE operations
            SET completion = ?
            WHERE id = ?
            """,
            ("REQUESTING PAUSE", operation_id),
        )
        db.commit()
        return {"operation_id": b64encode_id(operation_id), "success": True}

    return {
        "operation_id": b64encode_id(operation_id),
        "success": False,
        "message": "Invalid operation ID",
    }


@app.route("/operations/resume/<operation_id>", methods=("POST",))
@login_required
def resume(operation_id):
    operation_id = b64decode_id(operation_id)
    db = get_db()

    operation = db.execute(
        "SELECT * FROM operations WHERE id = ?", (operation_id,)
    ).fetchone()

    if operation and operation["completion"] == "PAUSED":
        with open(operation["workflow_store"]) as f:
            workflow = json.load(f)
        deserialize_chain(workflow)(operation["result"])

        db.execute(
            """
            UPDATE operations
            SET completion = ?
            WHERE id = ?
            """,
            ("IN PROGRESS", operation_id),
        )
        db.commit()
        return {"operation_id": b64encode_id(operation_id), "success": True}

    return {
        "operation_id": b64encode_id(operation_id),
        "success": False,
        "message": "Invalid operation ID",
    }


@app.route("/operations/cancel/<operation_id>", methods=("POST",))
@login_required
def cancel(operation_id):
    operation_id = b64decode_id(operation_id)
    db = get_db()

    operation = db.execute(
        "SELECT * FROM operations WHERE id = ?", (operation_id,)
    ).fetchone()

    if operation and operation["completion"] == "PAUSED":
        db.execute(
            """
            UPDATE operations
            SET completion = ?
            WHERE id = ?
            """,
            ("CANCELLED", operation_id),
        )
        db.commit()
        return {"operation_id": b64encode_id(operation_id), "success": True}

    return {
        "operation_id": b64encode_id(operation_id),
        "success": False,
        "message": "Invalid operation ID",
    }
