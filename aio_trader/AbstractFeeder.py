import asyncio
import logging
from abc import ABC, abstractmethod
from functools import wraps
from typing import Callable, Optional
import time

import aiohttp

logger = logging.getLogger(__name__)


def retry(max_retries=5, base_wait=2, max_wait=60, reset_retry_after=30):
    """
    Decorator that retries a function or method with exponential backoff
    in case of exceptions.

    Retry terminates if response code is 403: Session Expired

    :param max_retries: The maximum number of retry attempts. Default 50
    :type max_retries: int
    :param base_wait: The initial delay in seconds before the first retry. Default 2
    :type max_retries: float
    :param max_wait_time: The maximum delay in seconds between retries. Default 60
    :type max_wait_time: float

    Usage:

    .. code:: python

        @retry(max_retries=5, base_wait=2, max_wait=60)
        async def your_function_or_method(*args, **kwargs):
            # Your function or method logic goes here
            pass
    """

    def decorator(method):
        @wraps(method)
        async def wrapper(instance, *args, **kwargs):
            retries = 0
            last_connection_time = None

            while retries < max_retries:
                try:
                    result = await method(instance, *args, **kwargs)
                    last_connection_time = time.monotonic()
                    return result
                except aiohttp.ClientResponseError as e:
                    await instance.close()
                    logger.warning(f"Client Response Error: {e.code} {e.message}")
                    return
                except (ConnectionError, aiohttp.ClientConnectionError) as e:
                    if (
                        last_connection_time
                        and time.monotonic() - last_connection_time > reset_retry_after
                    ):
                        logger.info("Connection was stable - resetting retry count")
                        retries = 0

                    logger.warning(f"Connection Error: {e}")

                    # Calculate the wait time using exponential backoff
                    wait = min(base_wait * (2**retries), max_wait)

                    logger.info(f"Retrying in {wait} seconds...")
                    await asyncio.sleep(wait)

                    retries += 1
                except Exception as e:
                    await instance.close()
                    logger.exception("An error occurred: %s", e)
                    return

            await instance.close()
            logger.warning("Exceeded maximum retry attempts. Exiting.")

        return wrapper

    return decorator


class AbstractFeeder(ABC):
    """
    Base class for all Market Feeds
    """

    on_tick: Callable
    on_connect: Optional[Callable] = None
    on_order_update: Optional[Callable] = None
    on_message: Optional[Callable] = None
    on_error: Optional[Callable] = None
    ws: aiohttp.ClientWebSocketResponse
    session: aiohttp.ClientSession
    WS_URL: str
    connected = False

    def __init__(self) -> None:
        self.ping_interval = 10

    async def __aenter__(self):
        """On entering async context manager"""
        return self

    async def __aexit__(self, *_):
        """On exiting async context manager"""
        await self.close()
        return False

    @abstractmethod
    async def connect(self):
        """Connect to websocket and handle incoming messages"""
        pass

    def _initialise_session(self):
        """Start a aiohttp.ClientSession"""
        tcp_connector = aiohttp.TCPConnector(
            ttl_dns_cache=375 * 60,
            resolver=aiohttp.resolver.AsyncResolver(),
        )

        self.session = aiohttp.ClientSession(
            skip_auto_headers=("User-Agent"),
            connector=tcp_connector,
        )

    @abstractmethod
    async def close(self):
        """Close the websocket connection and allow for graceful shutdown"""
        pass
