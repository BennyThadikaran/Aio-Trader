import asyncio
import json
import pathlib
from typing import Any, Dict, List, Optional

import aiohttp
from throttler import Throttler

from .utils import configure_default_logger


def retry(max_retries=5, base_wait=3, max_wait=30):
    """
    Decorator that retries a function or method with exponential backoff
    in case of exceptions.

    :param max_retries: The maximum number of retry attempts.
    :type max_retries: int
    :param base_wait: The initial delay in seconds before the first retry.
    :type base_wait: float
    :param max_wait: The maximum delay in seconds between retries.
    :type max_wait: float

    .. code::python

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
                    aiohttp.ClientConnectionError,
                    json.JSONDecodeError,
                    ConnectionError,
                ) as e:
                    instance.logger.warning(
                        f"Attempt {retries + 1} failed: {e}"
                    )

                    # Calculate the wait time using exponential backoff
                    wait = min(base_wait * (2**retries), max_wait)

                    instance.logger.info(f"Retrying in {wait} seconds...")
                    await asyncio.sleep(wait)

                    retries += 1
                except RuntimeError as e:
                    await instance.close_session()
                    return instance.logger.exception(f"An error occurred {e}")

            instance.logger.warn("Exceeded maximum retry attempts. Exiting.")

        return wrapper

    return decorator


class AsyncRequest:
    """
    A wrapper class for making async requests using aiohttp

    :param throttlers: Default list of throttlers to apply to all requests.
    :type throttlers: List[throttler.Throttler]
    :param kwargs: Additional keyword arguments passed to aiohttp.ClientSession

    """

    session: aiohttp.ClientSession

    def __init__(
        self,
        throttlers: List[Throttler],
        cookie_path: Optional[pathlib.Path] = None,
        **kwargs,
    ) -> None:
        self.session_args: Dict[str, Any] = kwargs
        self.logger = configure_default_logger(__name__)
        self.cookie_path = cookie_path

        self.throttlers = throttlers

    async def __aenter__(self):
        """On entering async context manager"""
        self.start_session()
        return self

    async def __aexit__(self, *_):
        """On exiting async context manager"""
        await self.close_session()

    def start_session(self):
        """Starts the aiohttp.ClientSession and maps the HTTP methods"""
        self.session = aiohttp.ClientSession(**self.session_args)
        self.fn_map = {
            "GET": self.session.get,
            "POST": self.session.post,
            "PUT": self.session.put,
            "DELETE": self.session.delete,
            "PATCH": self.session.patch,
        }

    async def close_session(self):
        """Close the session"""
        if not self.session.closed:
            await self.session.close()

    @retry(max_retries=5, base_wait=3, max_wait=30)
    async def __req(self, method, endpoint, **kwargs):
        """
        Make an http request using the specified HTTP method.

        :raise RuntimeError: if HTTP response code is 400, 403, 429
        :raise ConnectionError: for any other HTTP response error code

        """
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
        throttlers: Optional[List[Throttler]] = None,
    ) -> Any:
        """
        GET Request

        :param endpoint: url endpoint
        :type endpoint: str
        :param params: Query string params
        :type params: dict or any iterable
        :param headers: Additional http headers
        :type headers: dict
        :param throttlers: Default None. Overide the default throttlers
        :type throttlers: Optional[List[Throttler]]

        """
        t = throttlers or self.throttlers

        await self.__apply_throttle(t)

        return await self.__req("GET", endpoint, params=params, headers=headers)

    async def post(
        self,
        endpoint,
        data=None,
        params=None,
        json=None,
        headers=None,
        throttlers: Optional[List[Throttler]] = None,
    ) -> Any:
        """
        POST Request

        :param endpoint: url endpoint
        :type endpoint: str
        :param data: data to send in body of POST request
        :type data: aiohttp.FormData or any object that can be passed to formdata
        :param params: data to send in body of POST request
        :type params: dict or any iterable
        :param json: Any json compatible python object (optional). json and
         data parameters could not be used at the same time.
        :type json: dict
        :param headers: Additional http headers
        :type headers: dict
        :param throttlers: Default None. Overide the default throttlers
        :type throttlers: Optional[List[Throttler]]
        """
        t = throttlers or self.throttlers

        await self.__apply_throttle(t)

        return await self.__req(
            "POST",
            endpoint,
            data=data,
            params=params,
            json=json,
            headers=headers,
        )

    async def put(
        self,
        endpoint,
        data=None,
        headers=None,
        throttlers: Optional[List[Throttler]] = None,
    ) -> Any:
        """PUT Request

        :param endpoint: url endpoint
        :type endpoint: str
        :param data: data to send in body of PUT request
        :type data: aiohttp.FormData or any object that can be passed to formdata
        :param headers: Additional http headers
        :type headers: dict
        :param throttlers: Default None. Overide the default throttlers
        :type throttlers: Optional[List[Throttler]]
        """
        t = throttlers or self.throttlers

        await self.__apply_throttle(t)

        return await self.__req("PUT", endpoint, data=data, headers=headers)

    async def delete(
        self,
        endpoint,
        data=None,
        json=None,
        headers=None,
        throttlers: Optional[List[Throttler]] = None,
    ) -> Any:
        """
        DELETE Request

        :param endpoint: url endpoint
        :type endpoint: str
        :param data: data to send in body of POST request
        :type data: aiohttp.FormData or any object that can be passed to formdata
        :param json: Any json compatible python object (optional). json and
         data parameters could not be used at the same time.
        :type json: dict
        :param headers: Additional http headers
        :type headers: dict
        :param throttlers: Default None. Overide the default throttlers
        :type throttlers: Optional[List[Throttler]]
        """
        t = throttlers or self.throttlers

        await self.__apply_throttle(t)

        return await self.__req(
            "DELETE", endpoint, headers=headers, data=data, json=json
        )

    async def patch(
        self,
        endpoint,
        data=None,
        headers=None,
        throttlers: Optional[List[Throttler]] = None,
    ) -> Any:
        """
        DELETE Request

        :param endpoint: url endpoint
        :type endpoint: str
        :param data: data to send in body of POST request
        :type data: aiohttp.FormData or any object that can be passed to formdata
        :param headers: Additional http headers
        :type headers: dict
        :param throttlers: Default None. Overide the default throttlers
        :type throttlers: Optional[List[Throttler]]
        """
        t = throttlers or self.throttlers

        await self.__apply_throttle(t)

        return await self.__req("PATCH", endpoint, headers=headers, data=data)

    @staticmethod
    async def __apply_throttle(throttlers: List[Throttler]):
        for t in throttlers:
            async with t:
                pass
