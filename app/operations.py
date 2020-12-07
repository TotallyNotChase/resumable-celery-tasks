import os
import json

from flask import render_template, redirect
from flask.globals import g
from flask.helpers import url_for

from app import app
from app.auth import login_required
from app.db import get_db
from app.tasks import (
    read_finish_continue,
    read_start,
    read_next,
    start_parsing,
    should_pause,
    save_state,
)
from app.tappable import tappable
from app.utils import deserialize_chain, b64encode_id, b64decode_id


@app.route("/operations")
@login_required
def operations_index():
    # Page to view all operations under a user
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
    # Get information about an operation by id
    operation_id = b64decode_id(operation_id)
    db = get_db()

    operation = db.execute(
        "SELECT * FROM operations WHERE id = ?", (operation_id,)
    ).fetchone()

    if operation["completion"] == "COMPLETED":
        # Load the result from json file if operation is complete
        with open(operation["result_store"], "r") as f:
            result = json.load(f)
    else:
        # Otherwise, result should just be an empty string
        result = ""
    return render_template(
        "operations/operation.html",
        operation_id=b64encode_id(operation_id),
        status=operation["completion"],
        result=result,
    )


@app.route("/operations/start", methods=("POST",))
@login_required
def start():
    # Start a csv reading + parsing operation
    db = get_db()

    # Insert a record of the operation and grab its id
    operation_id: int = db.execute(
        "INSERT INTO operations (requester_id, completion) VALUES (?, ?)",
        (g.user["id"], "IN PROGRESS"),
    ).lastrowid

    """
    Brief description of the operation
    ----------------------------------
    `read_start` initiates reading from the csv file
    `read_next`, then continues reading from the same file and
    merges its results with the previous read
    `read_finish_continue`, determines whether or not the file has been
    read in full and continues reading accordingly

    Once the iterative reading is finished, `start_parsing` is called
    to start the parsing operation
    """
    csvpath = os.path.join(app.instance_path, "MOCK_DATA.csv")
    # Start the operation, using the usual tappable configuration
    tappable(
        # Chain of data reading + callback to data parsing
        read_start.s(csvpath)
        | read_next.s(csvpath)
        | read_finish_continue.s(start_parsing.s(operation_id), csvpath, operation_id),
        # Function to check whether or not operation should pause
        should_pause.s(operation_id),
        # Pause handler
        save_state.s(operation_id),
    )()

    db.commit()
    return redirect(url_for("operation_info", operation_id=b64encode_id(operation_id)))


@app.route("/operations/pause/<operation_id>", methods=("POST",))
@login_required
def pause(operation_id):
    # Request an operation to pause
    operation_id = b64decode_id(operation_id)
    db = get_db()

    operation = db.execute(
        "SELECT * FROM operations WHERE id = ?", (operation_id,)
    ).fetchone()

    if operation and operation["completion"] == "IN PROGRESS":
        """
        Change operation status to "REQUESTING PAUSE" - next time
        the `app.tappable.pause_or_continue` task is called - it'll know
        it should pause
        """
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
    elif not operation:
        return {
            "operation_id": b64encode_id(operation_id),
            "success": False,
            "message": "Invalid operation ID",
        }
    else:
        return {
            "operation_id": b64encode_id(operation_id),
            "success": False,
            "message": "Operation is no longer in progress",
        }


@app.route("/operations/resume/<operation_id>", methods=("POST",))
@login_required
def resume(operation_id):
    # Resume an operation
    operation_id = b64decode_id(operation_id)
    db = get_db()

    operation = db.execute(
        "SELECT * FROM operations WHERE id = ?", (operation_id,)
    ).fetchone()

    if operation and operation["completion"] == "PAUSED":
        # Load the remaining workflow and the result (so far)
        with open(operation["workflow_store"]) as f:
            workflow = json.load(f)
        with open(operation["result_store"], "r") as f:
            result = json.load(f)
        # Initiate the remaining workflow and pass in the result
        # NOTE: The workflow itself is already tappable so pausing after
        # this point is also possible
        deserialize_chain(workflow)(result)

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
    elif not operation:
        return {
            "operation_id": b64encode_id(operation_id),
            "success": False,
            "message": "Invalid operation ID",
        }
    else:
        return {
            "operation_id": b64encode_id(operation_id),
            "success": False,
            "message": "Operation is not paused",
        }


@app.route("/operations/cancel/<operation_id>", methods=("POST",))
@login_required
def cancel(operation_id):
    # Cancel an operation altogether (only available after pausing)
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
    elif not operation:
        return {
            "operation_id": b64encode_id(operation_id),
            "success": False,
            "message": "Invalid operation ID",
        }
    else:
        return {
            "operation_id": b64encode_id(operation_id),
            "success": False,
            "message": "Operation is not paused",
        }