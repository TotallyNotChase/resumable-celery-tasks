import csv
import os
import json
from io import StringIO
from typing import Any, List, Dict, Tuple, Union

from celery.canvas import chain, signature

from app import app, celery
from app.db import get_db
from app.tappable import tappable
from app.utils import chunks_of, read_chunk

# How many bytes to read from file per task
READ_CHUNK_SIZE = 4096
# How many tasks to divide the csv parsing into (+-1)
PARSE_CHUNK_AMOUNT = 5


@celery.task()
def read_start(filename: str):
    """
    First task in the iterative csv reading operation

    Reads the first chunk from the given csv filename
    Parses it into csv and extracts the fieldnames
    Returns the fieldnames, next reading offset, and parsed csv
    as list of dicts - for the next task to process
    """
    (nxt, csv_content) = read_chunk(filename, 0, READ_CHUNK_SIZE)
    fst_csv = csv.DictReader(StringIO(csv_content))
    return fst_csv.fieldnames, nxt, [dict(row) for row in fst_csv]


@celery.task()
def read_next(prevres: Tuple[List[str], int, List[Dict[str, str]]], filename: str):
    """
    Continuation task in the iterative csv reading operation

    Expects fieldnames, reading offset and any previously parsed csv
    to be passed as its first argument

    Reads a chunk starting from given offset, parses it and passes next offset
    and new list of dicts (from previous + current csv read) results to the next task
    (along with the fieldnames from previous task)

    If the read from file yielded an empty string (EOF reached), returns **only**
    the final list of dicts (from previous + current csv read)
    """
    fieldnames, offset, accum = prevres
    (nxt, csv_content) = read_chunk(filename, offset, READ_CHUNK_SIZE)
    if csv_content == "":
        return (accum,)
    data = [
        dict(row)
        for row in csv.DictReader(StringIO(csv_content), fieldnames=fieldnames)
    ]
    return fieldnames, nxt, accum + data


@celery.task()
def read_finish_continue(
    prevres: Union[
        Tuple[List[str], int, List[Dict[str, str]]], Tuple[List[Dict[str, str]]]
    ],
    callback: dict,
    filename: str,
    operation_id: int,
):
    """
    NOTE: This task should be placed after each `read_next` task
    Checks whether the previous task (`read_next`) returned a tuple of 3
    results or 1

    If previous task returned a tuple of 3 results, it means EOF has not been reached
    and the operation should continue with another `read_next`

    If previous task returned a tuple of 1 result (just the final list of dicts), EOF has been reached
    - initiate the given callback (should be a serialized signature)
    """
    if len(prevres) == 3:
        # Continue with another `read_next`, `read_finish_continue` pair
        # Use the regular tappable configuration as well
        tappable(
            (
                read_next.s(filename)
                # Pass in the same callback, filename, and operation_id
                | read_finish_continue.s(callback, filename, operation_id)
            ),
            # Function to check whether or not operation should pause
            should_pause.s(operation_id),
            # Pause handler
            save_state.s(operation_id),
            # Start the chain with the previous result (tuple of 3 elements: see `read_next`)
        ).delay(prevres)
        # Just a dummy return to aid in logging - doesn't really serve a purpose
        return "Continuing reading"
    else:
        # EOF reached, finished reading - initiate the callback task and pass it the final list of dicts
        signature(callback).delay(prevres[0])
        # Just a dummy return to aid in logging - doesn't really serve a purpose
        return "Finished Reading"


@celery.task()
def start_parsing(retval: List[Dict[str, str]], operation_id: int):
    """
    First task in the iterative parsing operation
    The parsing operation just counts the number of male and female employees
    in each company and puts the results in a dicth of shape
    `{ company: { Male: int, Female: int } }`
    This is just a basic operation to demonstrate the workflow

    Divides the data to parse (list of dicts) into chunks
    Prepares the starting accumulator, a dict with all companies as key and
    `0` as `Male` and `Female` employee count starting values for each company

    Then the chunked data is used to create a chain of `count_ratio` tasks
    The `completion` task is chained at the end
    Ofcourse, the whole operation follows the regular tappable configuration

    NOTE: This operation depends on the previous chunk's results
    hence it's not suitable for `celery.chunks` - which is why a *chain*
    of manual chunks is used instead

    This is mathematically comparable to a `fold` operation - the `accum` serves the same
    purpose here as it does in a `fold` operation. Celery's own `chunks` is a parallel `map`
    operation (which will still be useful for certain workflows)
    """
    parse_chunks = chunks_of(retval, PARSE_CHUNK_AMOUNT)
    starting_accum = {entry["company"]: {"Male": 0, "Female": 0} for entry in retval}
    tappable(
        # A `fold` of `parse_chunks` over `count_ratio` tasks with a final callback `completion`
        chain(
            *[count_ratio.s(parse_chunk) for parse_chunk in parse_chunks],
            completion.s(operation_id),
        ),
        # Function to check whether or not operation should pause
        should_pause.s(operation_id),
        # Pause handler
        save_state.s(operation_id),
        nth=2,
        # Pass the starting value for the `fold` operation
    ).delay(starting_accum)


@celery.task()
def count_ratio(accum: Dict[str, Dict[str, int]], data: List[Dict[str, str]]):
    """
    Go through the list of dicts and tally the number of male and female
    employees of each company into `accum`

    Return the new `accum` for the next task to process

    NOTE: Yes, technically `accum` is already mutated in place due to property access
    and doesn't actually need to be returned - however, both celery itself, and this demo
    operation follows functional philosophies (due to it being a `fold` operation) - so the
    return value should still be used instead
    """
    for entry in data:
        accum[entry["company"]][entry["gender"]] += 1
    return accum


@celery.task()
def completion(retval: dict, operation_id: int):
    # Task to call when an operation workflow finishes
    db = get_db()

    # Prepare directories to store the result
    operation_dir = os.path.join(app.config["OPERATIONS"], f"{operation_id}")
    result_file = os.path.join(operation_dir, "result.json")
    if not os.path.isdir(operation_dir):
        os.makedirs(operation_dir, exist_ok=True)

    # Store the result into a file
    with open(result_file, "w") as f:
        json.dump(retval, f)

    # Store result metadata into the database
    db.execute(
        """
        UPDATE operations
        SET completion = ?,
            workflow_store = ?,
            result_store = ? 
        WHERE id = ?
        """,
        ("COMPLETED", None, result_file, operation_id),
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
def save_state(retval: Any, chains: List[dict], operation_id: int):
    # This is the `callback` to be used for `tappable`
    # i.e this is called when an operation is pausing
    db = get_db()

    # Prepare directories to store the workflow
    operation_dir = os.path.join(app.config["OPERATIONS"], f"{operation_id}")
    workflow_file = os.path.join(operation_dir, "workflow.json")
    result_file = os.path.join(operation_dir, "result.json")
    if not os.path.isdir(operation_dir):
        os.makedirs(operation_dir, exist_ok=True)

    # Store the remaining workflow chain, serialized into json
    with open(workflow_file, "w") as f:
        json.dump(chains, f)

    # Also store the result (so far) into a file
    with open(result_file, "w") as f:
        json.dump(retval, f)

    # Store the result from the last task and the workflow json path
    db.execute(
        """
        UPDATE operations
        SET completion = ?,
            workflow_store = ?,
            result_store = ?
        WHERE id = ?
        """,
        ("PAUSED", workflow_file, result_file, operation_id),
    )
    db.commit()
