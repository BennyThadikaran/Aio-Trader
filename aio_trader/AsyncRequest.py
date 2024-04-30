from typing import Any, Dict, Optional, Any
import logging
import asyncio
import aiohttp
from throttler import Throttler
import json


def retry(max_retries=50, base_wait=2, max_wait=60):
    """
    Decorator that retries a function or method with exponential backoff
    in case of exceptions.

    Parameters:
    - max_retries (int): The maximum number of retry attempts.
    - base_wait (float): The initial delay in seconds before the first retry.
    - max_wait (float): The maximum delay in seconds between retries.

    Usage:
    @retry(max_retries=5, base_wait=2, max_wait=60)
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
                except (
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    json.JSONDecodeError,
                    ConnectionError,
                ) as e:
                    instance.logger.warn(f"Attempt {retries + 1} failed: {e}")

                    # Calculate the wait time using exponential backoff
                    wait = min(base_wait * (2**retries), max_wait)

                    instance.logger.info(f"Retrying in {wait} seconds...")
                    await asyncio.sleep(wait)

                    retries += 1
                except RuntimeError as e:
                    instance.logger.warn(str(e))
                    await instance.close_session()
                    raise e

            instance.logger.warn("Exceeded maximum retry attempts. Exiting.")

        return wrapper

    return decorator


class AsyncRequest:
    """
    A wrapper class for making async requests using aiohttp

    Methods can raise
        - RuntimeError
        - ConnectionError
        - asyncio.TimeoutError

    :param logger: A logging.Logger instance
    :type logger: logging.Logger
    :param throttle: Default throttler for all requests.
    :type throttle: throttler.Throttler
    :param **kwargs: Additional keyword arguments passed to aiohttp.ClientSession
    """

    session: aiohttp.ClientSession
    throttle: Throttler

    def __init__(
        self,
        logger: logging.Logger,
        throttle: Optional[Throttler] = None,
        cookie_path: Optional[pathlib.Path] = None,
        **kwargs,
    ) -> None:
        self.session_args: Dict[str, Any] = kwargs
        self.logger = logger
        self.cookie_path = cookie_path

        if throttle is None:
            raise RuntimeError("Default Throttler is required")

        self.throttle = throttle

    async def __aenter__(self):
        self.start_session()
        return self

    async def __aexit__(self, *_):
        await self.close_session()

    def start_session(self):
        self.session = aiohttp.ClientSession(**self.session_args)
        self.fn_map = {
            "GET": self.session.get,
            "POST": self.session.post,
            "PUT": self.session.put,
            "DELETE": self.session.delete,
        }

    async def close_session(self):
        if not self.session.closed:
            await self.session.close()

    @retry(max_retries=5, base_wait=3, max_wait=30)
    async def __req(self, method, endpoint, **kwargs):
        async with self.fn_map[method](endpoint, **kwargs) as response:
            if response.ok:
                self.cookies = response.cookies

                if response.content_type == "application/json":
                    return await response.json(content_type=None)

                # text/plain or text/html
                if response.content_type in ("text/plain", "text/html"):
                    return await response.text()

                # Bytes response
                return await response.read()

            if response.status == 400:
                raise RuntimeError("400: Incorrect method or params")

            if response.status == 429:
                raise RuntimeError("429: API Rate limit reached.")

            if response.status == 403:
                if self.cookie_path and self.cookie_path.exists():
                    self.cookie_path.unlink()
                    self.logger.info(
                        "Cookie file deleted. Try logging in again"
                    )

                raise RuntimeError("403: Forbidden")

            raise ConnectionError(f"{response.status}: {response.reason}")

    async def get(
        self,
        endpoint,
        params=None,
        headers=None,
        throttle: Optional[Throttler] = None,
    ) -> Any:
        """
        GET Request

        :param endpoint: url endpoint
        :type str
        :param params: Query string params
        :type params: dict
        :param headers: Additional http headers
        :type dict
        :param throttle: Overide the default throttler
        :type throttle.Throttler
        """

        t = throttle if throttle else self.throttle

        async with t:
            return await self.__req(
                "GET", endpoint, params=params, headers=headers
            )

    async def post(
        self,
        endpoint,
        data=None,
        params=None,
        headers=None,
        throttle: Optional[Throttler] = None,
    ) -> Any:
        """
        POST Request

        :param endpoint: url endpoint
        :type str
        :param data: data to send in body of POST request
        :type params: aiohttp.FormData
        :param headers: Additional http headers
        :type dict
        :param throttle: Overide the default throttler
        :type throttle.Throttler
        """
        t = throttle if throttle else self.throttle

        async with t:
            return await self.__req(
                "POST", endpoint, data=data, params=params, headers=headers
            )

    async def put(
        self,
        endpoint,
        data=None,
        headers=None,
        throttle: Optional[Throttler] = None,
    ) -> Any:
        """PUT Request

        :param endpoint: url endpoint
        :type str
        :param data: data to send in body of PUT request
        :type params: aiohttp.FormData
        :param headers: Additional http headers
        :type dict
        :param throttle: Overide the default throttler
        :type throttle.Throttler
        """
        t = throttle if throttle else self.throttle

        async with t:
            return await self.__req("PUT", endpoint, data=data, headers=headers)

    async def delete(
        self,
        endpoint,
        headers=None,
        throttle: Optional[Throttler] = None,
    ) -> Any:
        """DELETE Request

        :param endpoint: url endpoint
        :type str
        :param headers: Additional http headers
        :type dict
        :param throttle: Overide the default throttler
        :type throttle.Throttler
        """
        t = throttle if throttle else self.throttle

        async with t:
            return await self.__req("DELETE", endpoint, headers=headers)
