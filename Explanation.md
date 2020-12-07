With [celery workflows](https://docs.celeryproject.org/en/stable/userguide/canvas.html) - you can design your entire operation to be divided into a [`chain`](https://docs.celeryproject.org/en/stable/userguide/canvas.html#chains) of tasks. It doesn't necessarily have to be purely a chain, but it should follow the general concept of one task after another task (or task [`group`](https://docs.celeryproject.org/en/stable/userguide/canvas.html#groups)) finishes.

Once you have a workflow like that, you can *finally define* points to pause at throughout your workflow. At *each* of these points, you can check whether or not the frontend user has **requested the operation to pause** and continue accordingly. The concept is this:-

A complex and time consuming operation O is split into 5 celery tasks - T1, T2, T3, T4, and T5 - each of these tasks (except the first one) depend on the return value of the previous task. 

Let's assume we define points to pause *after every single task*, so the workflow looks like-
* T1 executes
* T1 completes, check if user has requested pause
  * If user has not requested pause - continue
  * If user has requested pause, **serialize** the *remaining workflow chain* and store it somewhere to continue later

... and so on. Since there's a pause point after each task, that check is performed after every one of them (except the last one of course).

But this is only theory, I struggled to find an implementation of this anywhere online so here's what I came up with-
# Implementation
*The implementation can be seen in [`tappable.py`](./app/tappable.py)

## Explanation - `pause_or_continue`
Here `pause_or_continue` is the aforementioned *pause point*. It's a task that will be called at specific intervals (intervals as in task intervals, not as in time intervals). This task then calls a user provided function (actually a task) - `clause` - to check whether or not the task should continue.

If the `clause` function (actually a task) returns `True`, the user provided `callback` function is called, the latest return value (if any - `None` otherwise) is passed onto this callback, as well as the **remaining chain of tasks**. The `callback` does what it needs to do and `pause_or_continue` sets `self.request.chain` to `None`, which tells celery "The task chain is now empty - everything is finished".

If the `clause` function (actually a task) returns `False`, the return value from the previous task (if any - `None` otherwise) is returned back for the next task to receive - and the chain goes on. Hence the workflow continues.

### Why are `clause` and `callback` task signatures and not regular functions?
Both `clause` and `callback` are being called *directly* - without `delay` or `apply_async`. It is executed in the current process, in the current context. So it behaves exactly like a normal function, then why use [`signatures`](https://docs.celeryproject.org/en/stable/userguide/canvas.html#signatures)?

The answer is serialization. You can't conveniently pass a regular function object to a celery task. But you *can* pass a task signature. That's exactly what I'm doing here. Both `clause` and `callback` should be a **regular** `signature` object of a celery task.

### What is `self.request.chain`?
`self.request.chain` stores a list of dicts (representing jsons as the celery task serializer is json by default) - each of them representing a task signature. Each task from this list is executed in reverse order. Which is why, the list is reversed before passing to the user provided `callback` function (actually a task) - the user probably expects the order of tasks to be left to right.

**Quick note**: Irrelevant to this discussion, but if you're using the `link` parameter from `apply_async` to construct a chain instead of the `chain` primitive itself. `self.request.callback` is the property to be modified (i.e set to `None` to remove callback and stop chain) instead of `self.request.chain`

## Explanation - `tappable`
`tappable` is just a basic function that takes a chain (which is the only workflow primitive covered here, for brevity) and inserts `pause_or_continue` after every `nth` task. You can insert them wherever you want really, it is upto you to define pause points in your operation. This is just an example!

For each `chain` object, the actual signatures of tasks (in order, going from left to right) is stored in the `.tasks` property. It's a *tuple* of task signatures. So all we have to do, is take this tuple, convert into a list, insert the pause points and convert back to a tuple to assign to the chain. Then return the modified chain object.

The `clause` and `callback` is also attached to the `pause_or_continue` signature. Normal celery stuff.

That covers the primary concept, but to showcase a real project using this pattern (and also to showcase the resuming part of a paused task), here's a small demo of all the necessary resources
# Usage
This example usage assumes the concept of a basic web server with a database. Whenever an operation (i.e workflow chain) is started, it's *assigned an id* and stored into the database. The schema of that table looks like-
```sql
-- Create operations table
-- Keeps track of operations and the users that started them
CREATE TABLE operations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  requester_id INTEGER NOT NULL,
  completion TEXT NOT NULL,
  workflow_store TEXT,
  result TEXT,
  FOREIGN KEY (requester_id) REFERENCES user (id)
);
```
The only field that needs to be known about right now, is `completion`. It just stores the status of the operation-

* When the operation starts and a db entry is created, this is set to `IN PROGRESS`
* When a user requests pause, the route controller (i.e view) modifies this to `REQUESTING PAUSE`
* When the operation actually gets paused and `callback` (from `tappable`, inside `pause_or_continue`) is called, the `callback` should modify this to `PAUSED`
* When the task is completed, this should be modified to `COMPLETED`

## An example of `clause`
```py
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
```
This is the task to call at the pause points, to determine whether or not to pause. It's a function that takes 2 parameters.....well sort of. The first one is mandatory, `tappable` *requires* the `clause` to have one (and exactly one) argument - so it can pass the previous task's return value to it (even if that return value is `None`). In this example, the return value isn't required to be used - so we can just ignore it.

The second parameter is an operation id. See, all this `clause` does - is check a database for the operation (the workflow) entry and see if it has the status `REQUESTING PAUSE`. To do that, it needs to know the operation id. But `clause` should be a task with one argument, what gives?

Well, good thing signatures can be partial. When the task is first started and a `tappable` chain is created. The operation id *is known* and hence we can do `should_pause.s(operation_id)` to get the signature of a task that takes **one** parameter, that being the return value of the previous task. That qualifies as a `clause`!

## An example of `callback`
```py
import os
import json
from typing import Any, List

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
```
And here's the task to be called when the task *is being paused*. Remember, this should take the last executed task's return value and the remaining list of signatures (in order, from left to right). There's an extra param - `operation_id` - once again. The explanation for this is the same as the one for `clause`.

This function stores the remaining chain in a json file (since it's a list of dicts). Remember, you can use a different serializer - I'm using json since it's the default task serializer used by celery.

After storing the remaining chain, it updates the `completion` status to `PAUSED` and also logs the path to the json file into the db.

Now, let's see these in action-
## An example of starting the workflow
```py
def start_operation(user_id, *operation_args, **operation_kwargs):
    db = get_db()
    operation_id: int = db.execute(
        "INSERT INTO operations (requester_id, completion) VALUES (?, ?)",
        (user_id, "IN PROGRESS"),
    ).lastrowid
    # Convert a regular workflow chain to a tappable one
    tappable_workflow = tappable(
        (T1.s() | T2.s() | T3.s() | T4.s() | T5.s(operation_id)),
        should_pause.s(operation_id),
        save_state.s(operation_id),
    )
    # Start the chain (i.e send task to celery to run asynchronously)
    tappable_workflow(*operation_args, **operation_kwargs)
    db.commit()
    return operation_id
```
A function that takes in a user id and starts an operation workflow. This is more or less an impractical dummy function modeled around a view/route controller. But I think it gets the general idea through.

Assume `T[1-4]` are all unit tasks of the operation, each taking the previous task's return as an argument. Just an example of a regular celery chain, feel free to go wild with your chains.

`T5` is a task that saves the final result (result from `T4`) to the database. So along with the return value from `T4` it needs the `operation_id`. Which is passed into the signature.

## An example of pausing the workflow
```py
def pause(operation_id):
    db = get_db()

    operation = db.execute(
        "SELECT * FROM operations WHERE id = ?", (operation_id,)
    ).fetchone()

    if operation and operation["completion"] == "IN PROGRESS":
        # Pause only if the operation is in progress
        db.execute(
            """
            UPDATE operations
            SET completion = ?
            WHERE id = ?
            """,
            ("REQUESTING PAUSE", operation_id),
        )
        db.commit()
        return 'success'

    return 'invalid id'
```
This employs the previously mentioned concept of modifying the db entry to change `completion` to `REQUESTING PAUSE`. Once this is committed, the next time `pause_or_continue` calls `should_pause`, it'll know that the user has requested the operation to pause and it'll do so accordingly.

## An example of resuming the workflow
```py
def resume(operation_id):
    db = get_db()

    operation = db.execute(
        "SELECT * FROM operations WHERE id = ?", (operation_id,)
    ).fetchone()

    if operation and operation["completion"] == "PAUSED":
        # Resume only if the operation is paused
        with open(operation["workflow_store"]) as f:
            # Load the remaining workflow from the json
            workflow_json = json.load(f)
        # Load the chain from the json (i.e deserialize)
        workflow_chain = chain(signature(x) for x in serialized_ch)
        # Start the chain and feed in the last executed task result
        workflow_chain(operation["result"])

        db.execute(
            """
            UPDATE operations
            SET completion = ?
            WHERE id = ?
            """,
            ("IN PROGRESS", operation_id),
        )
        db.commit()
        return 'success'

    return 'invalid id'
```
Recall that, when the operation is paused - the remaining workflow is stored in a json. Since we are currently restricting the workflow to a `chain` object. We know this json is a list of signatures that should be turned into a `chain`. So, we deserialize it accordingly and send it to the celery worker.

Note that, this remaining workflow still has the `pause_or_continue` tasks as they were originally - so this workflow itself, is once again pause-able/resume-able. When it pauses, the `workflow.json` will simply be updated.
