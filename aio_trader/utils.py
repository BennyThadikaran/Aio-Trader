from collections.abc import Callable
import logging, signal, asyncio
from typing import Any, List, AsyncGenerator


def configure_default_logger(name) -> logging.Logger:
    """Return a configured logger"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    return logging.getLogger(name)


def add_signal_handlers(handler: Callable, *args: Any, **kwargs: Any):
    """
    Add signal handlers for KeyboardInterrupt and terminate/kill commands

    handler must be an async function. It is used to perform clean up resources
    and allows graceful shutdown.

    Any positional or keyword arguments are passed to the handler
    """

    loop = asyncio.get_event_loop()

    for i in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            i, lambda: asyncio.create_task(handler(*args, **kwargs))
        )


async def as_completed(
    tasks: List[asyncio.Task],
) -> AsyncGenerator[asyncio.Task, None]:
    """
    source: https://stackoverflow.com/a/55531688

    When calling asyncio.as_completed, results are not returned
    in insertion order, but in the order of completion.

    The result is a coroutine object and not the original Task object.
    There is no link to the original Task, so any context information like the
    Task name is lost forever.

    Every task must be assigned a name, providing some context information.

    ```
    task = asyncio.create_task(fn, name='my_task')
    task.get_name() # my_task
    ```

    This function creates a Futures object and adds the `Futures.set_result`
    method as a callback to the task.

    The futures are added to a list and passed to `asyncio.as_completed`
    awaiting completion.

    When the task is completed, the callback (`Futures.set_result`) is called.
    It receives the completed task object marks the Futures object as done.

    Usage:

    ```
    # tasks: List[asyncio.Task]

    async for task in as_completed(tasks):
        name = task.get_name()
        result = task.result()
    ```

    Read the in-code documentation for further understanding.
    """
    loop = asyncio.get_event_loop()
    futures_list: List[asyncio.Future] = []

    for task in tasks:
        # create a asyncio.Future object
        future = loop.create_future()

        # When the task is completed, run the callback provided.
        # Future.set_result marks the future as done, and sets it result
        # The callback receives the completed task object
        task.add_done_callback(future.set_result)

        futures_list.append(future)

    # as tasks are completed, the future is marked as done
    for completed_future in asyncio.as_completed(futures_list):
        # await the future to yield the original task
        yield await completed_future
