import asyncio
import json
from typing import Dict, Optional

import aiohttp

from aio_trader.utils import configure_default_logger

from ..AbstractFeeder import AbstractFeeder, retry
from . import maps


class FyersOrder(AbstractFeeder):
    """
    Websocket class for Fyers Order Websocket

    .. py:property:: FyersOrder.on_tick
       :type: Callable[[FyersOrder, Dict[str, Any], bool], None]

       A user defined function called, when an order notification is received.
       It receives the order dictionary and a bool value indicating if the
       order message is parsed.

       def on_tick(feed: FyersOrder, order: dict, binary=False) -> None

    :param access_token: Fyers `access_token`.
    :type access_token: str
    :param session: Client Session for making HTTP requests.
    :type session: Optional[aiohttp.ClientSession].
    :param parse_data: If true, `on_tick` handler receives raw binary/text data. Default True.
    :type parse_data: bool
    """

    WSS_URL = "wss://socket.fyers.in/trade/v3"

    def __init__(
        self,
        access_token: str,
        session: Optional[aiohttp.ClientSession],
        parse_data: bool = True,
    ) -> None:

        super().__init__()

        self.parse_data = parse_data
        self.access_token = access_token

        self.connected = False
        self._shared_session = bool(session)

        self.log = configure_default_logger(__name__)

        self.loop = asyncio.get_running_loop()

        if session:
            self.session = session
        else:
            self._initialise_session()

        self.socket_type = {
            "OnOrders": "orders",
            "OnTrades": "trades",
            "OnPositions": "positions",
            "OnGeneral": ["edis", "pricealerts", "login"],
        }

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
        """Connect and start the Websocket connection

        :param kwargs: Any keyword arguments to pass to `aiohttp.ClientSession.ws_connect`
        :type: kwargs: Any
        """

        async with self.session.ws_connect(
            self.WSS_URL, heartbeat=self.ping_interval, **kwargs
        ) as ws:

            self.ws = ws

            if self.ws.closed:
                self.log.warning("Connection failed")
                return

            self.connected = True
            self.log.info("Subscribed to order updates")

            async for msg in self.ws:
                if msg == "pong":
                    continue

                if not self.parse_data:
                    return self.on_tick(msg.data)

                data = json.loads(msg.data)

                if "orders" in data:
                    processed = self.__parse_order_data(data)
                elif "positions" in data:
                    processed = self.__parse_position_data(data)
                elif "trades" in data:
                    processed = self.__parse_trade_data(data)
                else:
                    processed = data

                self.on_tick(processed)

    async def subscribe(self, data_type: str) -> None:
        """
        Subscribes to real-time updates of a specific data type.

        await subscribe(data_type="OnOrders")

        await subscribe(data_type="OnOrders,OnTrades,OnPositions,OnGeneral")

        :param data_type: Can be one of `OnOrders`, `OnTrades`, `OnPositions`, or `OnGeneral`, or a comma separated list of values
        :type data_type: str
        """
        if not hasattr(self, "ws") or self.ws.closed:
            return

        self.data_type = []

        for elem in data_type.split(","):
            if isinstance(self.socket_type[elem], list):
                self.data_type.extend(self.socket_type[elem])
            else:
                self.data_type.append(self.socket_type[elem])

        await self.ws.send_json(
            dict(T="SUB_ORD", SLIST=self.data_type, SUB_T=1)
        )

    async def unsubscribe(self, data_type: str) -> None:
        """
        Unsubscribes from real-time updates of a specific data type.

        await unsubscribe(data_type="OnOrders")

        await unsubscribe(data_type="OnOrders,OnTrades,OnPositions,OnGeneral")

        :param data_type: Can be one of `OnOrders`, `OnTrades`, `OnPositions`, or `OnGeneral`, or a comma separated list of values
        :type data_type: str
        """

        if not hasattr(self, "ws") or self.ws.closed:
            return

        self.data_type = tuple(
            self.socket_type[_type] for _type in data_type.split(",")
        )

        await self.ws.send_json(
            dict(T="SUB_ORD", SLIST=self.data_type, SUB_T=-1)
        )

    def __parse_position_data(self, msg: Dict) -> Dict:
        """
        Parses position data from a message and returns it in a specific format.

        Args:
            msg (str): The message containing position data.

        Returns:
            Dict[str, Any] : The parsed position data in a specific format.

        """
        position_data = {}

        for key, value in maps.positions_map.items():
            if key in msg["positions"]:
                position_data[value] = msg["positions"][key]

        return {"s": msg["s"], "positions": position_data}

    def __parse_trade_data(self, msg: Dict) -> Dict:
        """
        Parses trade data from a message and returns it in a specific format.

        Args:
            msg (str): The message containing trade data.

        Returns:
            Dict[str, Any] : The parsed trade data in a specific format.

        """
        trade_data = {}
        for key, value in maps.trade_map.items():
            if key in msg["trades"]:
                trade_data[value] = msg["trades"][key]

        return {"s": msg["s"], "trades": trade_data}

    def __parse_order_data(self, msg: Dict) -> Dict:
        """
        Parses order update data from a dictionary and returns it in a specific format.

        Args:
            msg (Dict[str, Any]): The dictionary containing order update data.

        Returns:
            Dict[str, Any]: The parsed order update data in a specific format.
        """
        order_data = {}
        for key, value in maps.order_map.items():
            if key in msg["orders"]:
                order_data[value] = msg["orders"][key]
        order_data["orderNumStatus"] = (
            msg["orders"]["id"] + ":" + str(msg["orders"]["org_ord_status"])
        )
        return {"s": msg["s"], "orders": order_data}
