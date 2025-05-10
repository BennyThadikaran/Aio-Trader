from collections.abc import Callable
import logging, signal, asyncio
from typing import Any, List, AsyncGenerator


def configure_default_logger(name="aio_trader") -> logging.Logger:
    """Return a configured logger

    :param name: Name of logger instance to be returned. Default `aio_trader`
    :type name: str
    """
    logger = logging.getLogger(name)
    formatter = logging.Formatter("%(levelname)s: %(message)s")

    logger.setLevel(logging.INFO)

    stdout_handler = logging.StreamHandler()
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(DIR / "error.log")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(formatter)

    logger.addHandler(stdout_handler)
    logger.addHandler(file_handler)

    return logger


def add_signal_handlers(handler: Callable, *args: Any, **kwargs: Any) -> None:
    """
    Add signal handlers for KeyboardInterrupt and terminate/kill commands.

    Any positional or keyword arguments are passed to handler

    :param handler: Async function to perform clean up operations before shutdown.
    :type handler: Callable
    :param args: Positional arguments to pass to handler function
    :type args: Any
    :param kwargs: Keyword arguments to pass to handler function
    :type kwargs: Any
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
    Similar to `asyncio.as_completed` but returns the original Task object.

    Source: https://stackoverflow.com/a/55531688

    :param tasks: A list of Task objects
    :type tasks: List[asyncio.Task]
    :return: AsyncGenerator[asyncio.Task, None]

    When calling asyncio.as_completed, results are not returned
    in insertion order, but in the order of completion.

    The result is a `Coroutine` object and not the original `Task` object.
    There is no link to the original Task, so any context information like the
    Task name is lost forever.

    **Code Explanation**:

    Every task must be assigned a name, providing some context information.

    .. code:: python

        task = asyncio.create_task(fn, name='my_task')
        task.get_name() # my_task

    This function creates a Futures object and adds the :py:obj:`Futures.set_result`
    method as a callback to the task.

    The futures are added to a list and passed to :py:obj:`asyncio.as_completed`
    awaiting completion.

    When the task is completed, the callback is called.
    It receives the completed task object and marks the Futures object as done.

    **Usage**:

    .. code:: python

        # tasks: List[asyncio.Task]

        async for task in as_completed(tasks):
            name = task.get_name()
            result = task.result()

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


if __name__ != "__main__":
    DIR = Path(__file__).parent
