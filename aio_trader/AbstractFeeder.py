import asyncio, aiohttp
from abc import ABC, abstractmethod
from typing import Callable, List, Optional, Union, Dict


def retry(max_retries=50, base_wait=2, max_wait=60):
    """
    Decorator that retries a function or method with exponential backoff
    in case of exceptions.

    Parameters:
    - max_retry_attempts (int): The maximum number of retry attempts.
    - base_wait_time (float): The initial delay in seconds before the first retry.
    - max_wait_time (float): The maximum delay in seconds between retries.

    Usage:
    @retry(max_retry_attempts=5, base_wait_time=2, max_wait_time=60)
    async def your_function_or_method(*args, **kwargs):
        # Your function or method logic goes here
        pass
    """

    def decorator(method):

        async def wrapper(instance, *args, **kwargs):
            retries = 0

            while retries < max_retries:
                try:
                    return await method(instance, *args, **kwargs)
                except Exception as e:
                    if (
                        isinstance(e, aiohttp.WSServerHandshakeError)
                        and getattr(e, "status") == 403
                    ):
                        await instance.close()
                        return instance.log.warn(
                            f"Session expired or invalid. Must relogin"
                        )

                    instance.log.warn(f"Operation failed: {e}")

                    # Calculate the wait time using exponential backoff
                    wait = min(base_wait * (2**retries), max_wait)

                    instance.log.info(f"Retrying in {wait} seconds...")
                    await asyncio.sleep(wait)

                    retries += 1

            instance.log.warn("Exceeded maximum retry attempts. Exiting.")

        return wrapper

    return decorator


class AbstractFeeder(ABC):
    """
    Base class for all Market Feeds
    """

    on_connect: Optional[Callable] = None
    on_tick: Optional[Callable] = None
    on_order_update: Optional[Callable] = None
    on_message: Optional[Callable] = None
    on_error: Optional[Callable] = None
    ws: aiohttp.ClientWebSocketResponse
    session: aiohttp.ClientSession
    WS_URL: str
    connected = False

    def __init__(self) -> None:
        self.ping_interval = 2.5

    @abstractmethod
    async def connect(self):
        pass

    def _initialise_session(self):
        tcp_connector = aiohttp.TCPConnector(
            ttl_dns_cache=375 * 60,
            resolver=aiohttp.resolver.AsyncResolver(),
        )

        self.session = aiohttp.ClientSession(
            skip_auto_headers=("User-Agent"),
            connector=tcp_connector,
        )

    def run_forever(self):
        asyncio.get_event_loop().run_until_complete(self.connect())

    @abstractmethod
    async def close(self):
        pass

    @abstractmethod
    def _parse_binary(self, bin) -> Union[List[Dict], Dict]:
        pass

    @abstractmethod
    async def subscribe_symbols(self, symbols: List[int], mode: str):
        pass

    @abstractmethod
    async def unsubscribe_symbols(self, symbols):
        pass
