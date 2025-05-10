import asyncio
import json
from typing import Optional

import aiohttp

from aio_trader.utils import configure_default_logger

from ..AbstractFeeder import AbstractFeeder, retry


class DhanOrder(AbstractFeeder):
    """
    Websocket class for Dhan Order Websocket

    .. py:property:: DhanOrder.on_tick
       :type: Callable[[DhanOrder, Dict[str, Any], bool], None]

       A user defined function called when order notification is received.
       Called with the order message as a dict and a bool value indicating
       if the order message is parsed.

       Must be attached to the class to receive order updates

       def on_tick(feed: DhanOrder, order: dict, binary=False) -> None

    :param access_token: Fyers `access_token`.
    :type access_token: str
    :param session: Client Session for making HTTP requests.
    :type session: Optional[aiohttp.ClientSession].
    :param parse_data: If true, `on_tick` handler receives raw binary/text data. Default True.
    :type parse_data: bool
    """

    WSS_URL = "wss://api-order-update.dhan.co"

    def __init__(
        self,
        client_id,
        access_token,
        session: Optional[aiohttp.ClientSession],
        parse_data: bool = True,
    ) -> None:

        super().__init__()

        self.parse_data = parse_data
        self.client_id = client_id
        self.access_token = access_token

        self.connected = False
        self._shared_session = bool(session)

        self.log = configure_default_logger(__name__)

        self.loop = asyncio.get_running_loop()

        if session:
            self.session = session
        else:
            self._initialise_session()

    async def close(self):
        """Perform clean up operations to gracefully exit"""

        if self.connected and hasattr(self, "ws") and not self.ws.closed:
            await self.ws.close()

        self.log.info("Order websocket closed")
        self.connected = False

        # Dont close the ClientSession, if it was initialized outside the class
        if self._shared_session:
            return

        if self.session and not self.session.closed:
            await self.session.close()

    @retry(max_retries=5, base_wait=2, max_wait=60)
    async def connect(self, **kwargs) -> None:
        """Connect to websocket and process any incomming messages

        Uses the retry decorator to reconnect if an error occurs
        @retry(max_retries=5, base_wait=2, max_wait=60)

        :param kwargs: Any keyword arguments to pass to `aiohttp.ClientSession.ws_connect`
        :type: kwargs: Any
        """

        async with self.session.ws_connect(
            self.WSS_URL, heartbeat=self.ping_interval, **kwargs
        ) as ws:

            self.ws = ws

            self.connected = not self.ws.closed

            auth_msg = dict(
                LoginReq=dict(
                    MsgCode=42,
                    ClientId=str(self.client_id),
                    Token=str(self.access_token),
                ),
                UserType="SELF",
            )

            await self.ws.send_json(auth_msg)
            self.log.info("Subscribed to order updates")

            async for msg in self.ws:
                self.on_tick(
                    json.loads(msg.data) if self.parse_data else msg.data
                )
