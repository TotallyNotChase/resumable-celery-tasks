import os
import time
import json
from typing import Any

from app import app, celery
from app.db import get_db


@celery.task()
def add(a: int, b: int):
    time.sleep(5)
    return a + b


@celery.task()
def mult(a: int, b: int):
    time.sleep(5)
    return a * b


@celery.task()
def completion(retval: Any, operation_id: int):
    # Task to call when an operation workflow finishes
    db = get_db()

    # Store final result into the database
    db.execute(
        """
        UPDATE operations
        SET completion = ?,
            workflow_store = ?,
            result = ? 
        WHERE id = ?
        """,
        ("COMPLETED", None, f"{retval}", operation_id),
    )
    db.commit()


@celery.task()
def should_pause(_, operation_id: int):
    # This is the `clause` to be used for `tappable`
    # i.e it lets celery know whether to pause or continue
    db = get_db()

    # Check the database to see if user has requested pause on the operation
    operation = db.execute(
        "SELECT * FROM operations WHERE id = ?", (operation_id,)
    ).fetchone()
    return operation["completion"] == "REQUESTING PAUSE"


@celery.task()
def save_state(retval: Any, chains: dict, operation_id: int):
    # This is the `callback` to be used for `tappable`
    # i.e this is called when an operation is pausing
    db = get_db()

    # Prepare directories to store the workflow
    operation_dir = os.path.join(app.config["OPERATIONS"], f"{operation_id}")
    workflow_file = os.path.join(operation_dir, "workflow.json")
    if not os.path.isdir(operation_dir):
        os.makedirs(operation_dir, exist_ok=True)
    
    # Store the remaining workflow chain, serialized into json
    with open(workflow_file, "w") as f:
        json.dump(chains, f)

    # Store the result from the last task and the workflow json path
    db.execute(
        """
        UPDATE operations
        SET completion = ?,
            workflow_store = ?,
            result = ?
        WHERE id = ?
        """,
        ("PAUSED", workflow_file, f"{retval}", operation_id),
    )
    db.commit()
