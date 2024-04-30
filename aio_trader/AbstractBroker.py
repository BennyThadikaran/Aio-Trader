from abc import ABC, abstractmethod
from aio_trader.AsyncRequest import AsyncRequest
from throttler import Throttler
import pathlib, aiohttp, logging


class AbstractBroker(ABC):
    """Base class for all Broker classes"""

    session: aiohttp.ClientSession
    cookie_path: pathlib.Path
    log: logging.Logger

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

        return False

    @abstractmethod
    async def authorize(self, **kwargs):
        """Authorize the user"""
        pass

    async def close(self):
        """Close the Requests session"""

        if self.session and not self.session.closed:
            await self.session.close()

    def _initialise_session(self, headers: dict, throttler: Throttler):
        """Start a aiohttp.ClientSession and assign a default throttler"""

        tcp_connector = aiohttp.TCPConnector(
            ttl_dns_cache=375 * 60, resolver=aiohttp.resolver.AsyncResolver()
        )

        self.req = AsyncRequest(
            logger=self.log,
            throttle=throttler,
            cookie_path=self.cookie_path,
            headers=headers,
            skip_auto_headers=("User-Agent"),
            connector=tcp_connector,
        )

        self.req.start_session()
        self.session = self.req.session
