"""
To avoid a task disappearing mid-execution a reference to the task needs to be saved. The event
loop only keeps weak references to tasks. A task that isn't referenced elsewhere may get garbage
collected at any time, even before it's done. For reliable "fire-and-forget" background tasks,
gather them in a collection.

https://docs.python.org/3/library/asyncio-task.html#creating-tasks
"""

import asyncio
from typing import Set

background_tasks: Set[asyncio.Task] = set()


def save_task_reference(task: asyncio.Task) -> None:
    """
    To avoid a task disappearing mid-execution a reference to the task needs to be saved.
    """
    # Add task to the set. This creates a strong reference.
    background_tasks.add(task)

    # To prevent keeping references to finished tasks forever,
    # make each task remove its own reference from the set after
    # completion:
    task.add_done_callback(background_tasks.discard)
