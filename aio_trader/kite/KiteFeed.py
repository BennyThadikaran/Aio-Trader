import asyncio
import json
import logging
import struct
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

import aiohttp

from aio_trader.utils import configure_default_logger

from ..AbstractFeeder import AbstractFeeder, retry


class KiteFeed(AbstractFeeder):
    """
    Websocket class for Zerodha Kite

    Implements the :py:obj:`AbstractFeeder` base class

    :param api_key: KiteConnect `api_key`. Default is "kitefront" for Web login.
    :type api_key: str
    :param user_id: Optional `user_id` for Kite Web login.
    :type user_id: Optional[str]
    :param enctoken: Optional `enctoken` for Kite Web login.
    :type enctoken: Optional[str]
    :param access_token: Optional KiteConnect `access_token`.
    :type access_token: Optional[str]
    :param parse_data: If true, `on_tick` handler receives raw binary/text data. Default True.
    :type parse_data: bool
    :param session: Client Session for making HTTP requests.
    :type session: Optional[aiohttp.ClientSession].
    :raises ValueError: If `enctoken` or `access_token` is not provided
    :raises ValueError: If `enctoken` is provided, but `user_id` is missing
    :raises ValueError: If `access_token` is provided, but `api_key` is the default value
    """

    WSS_URL = "wss://ws.zerodha.com"

    EXCH_MAP = {
        "nse": 1,
        "nfo": 2,
        "cds": 3,
        "bse": 4,
        "bfo": 5,
        "bcd": 6,
        "mcx": 7,
        "mcxsx": 8,
        "indices": 9,
        "bsecds": 6,
    }

    MODE_FULL = "full"
    MODE_QUOTE = "quote"
    MODE_LTP = "ltp"

    subscribed = {}
    ws: aiohttp.ClientWebSocketResponse

    def __init__(
        self,
        api_key: str = "kitefront",
        user_id: Optional[str] = None,
        enctoken: Optional[str] = None,
        access_token: Optional[str] = None,
        parse_data: bool = True,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        super().__init__()

        self.api_key = api_key
        self.user_id = user_id
        self.enctoken = enctoken
        self.access_token = access_token
        self.parse_data = parse_data
        self.connected = False
        self.loop = asyncio.get_event_loop()
        self._shared_session = bool(session)
        self.subscribed_tokens = dict()

        self.ping_interval = 2.5

        self.log = configure_default_logger(__name__)

        if not (self.enctoken or self.access_token):
            raise ValueError("Either enctoken or access_token is required.")

        if self.enctoken:
            if not self.user_id:
                raise ValueError("user_id is required with enctoken")

            self.auth_params = dict(
                api_key=self.api_key,
                user_id=self.user_id,
                enctoken=self.enctoken,
                agent="kite3-web",
                version="3.0.0",
            )

        if self.access_token:
            if self.api_key == "kitefront":
                raise ValueError("Invalid api_key for KiteConnect access_token")

            self.auth_params = dict(
                api_key=self.api_key,
                access_token=self.access_token,
            )

        if session:
            self.session = session
        else:
            self._initialise_session()

    async def close(self):
        """Perform clean up operations to gracefully exit"""

        if hasattr(self, "ws"):
            if not self.ws.closed:

                if self.subscribed:
                    await self.unsubscribe(list(self.subscribed_tokens.keys()))

                await self.ws.close()

        self.connected = False

        # Dont close the ClientSession, if it was initialized outside the class
        if self._shared_session:
            return

        if self.session and not self.session.closed:
            await self.session.close()

    async def _close(self, code=None, reason=None):
        self.log.error(f"{code}: {reason}")

        await self.close()

    @retry(max_retries=50, base_wait=2, max_wait=60)
    async def connect(self, **kwargs) -> None:
        """Connect and start the Websocket connection

        Use the retry decorator
        @retry(max_retries=50, base_wait=2, max_wait=60)


        :param kwargs: Any keyword arguments to pass to `aiohttp.ClientSession.ws_connect`
        :type: kwargs: Any
        """

        self.ws = await self.session.ws_connect(
            self.WSS_URL,
            heartbeat=self.ping_interval,
            params=self.auth_params,
            **kwargs,
        )

        if self.ws.closed:
            self.log.warning("Connection failed")
            return

        self.connected = True

        if self.on_connect:
            self.on_connect(self)

        async for msg in self.ws:
            # Ignore heartbeat pings
            if len(msg.data) == 1:
                continue

            is_binary = msg.type == aiohttp.WSMsgType.BINARY

            if not self.parse_data:
                self.on_tick(self, msg.data, binary=is_binary)
                continue

            fn = self._parse_binary if is_binary else self._parse_text

            data = fn(msg.data)

            if data:
                self.on_tick(self, data, binary=is_binary)

        await self.close()

    async def subscribe(self, instrument_tokens: Union[List[int], Tuple[int]]):
        """
        Subscribe to a list of instrument_tokens.

        :param instrument_tokens: A collection of instrument tokens
        :type instrument_tokens: List[int] | Tuple[int]
        """
        try:
            await self.ws.send_json(dict(a="subscribe", v=instrument_tokens))
        except Exception as e:
            await self._close(code=0, reason=f"Error while subscribe: {e!r}")
            return

        for token in instrument_tokens:
            self.subscribed_tokens[token] = self.MODE_QUOTE
            self.log.info(
                f"Subscribed to {len(instrument_tokens)} scripts with mode `quote`"
            )

    async def unsubscribe(
        self, instrument_tokens: Union[List[int], Tuple[int]]
    ):
        """
        Unsubscribe the given list of instrument_tokens.

        :param instrument_tokens: A collection of instrument tokens
        :type instrument_tokens: List[int] | Tuple[int]
        """
        try:
            await self.ws.send_json(dict(a="unsubscribe", v=instrument_tokens))

        except Exception as e:
            await self._close(code=0, reason=f"Error while unsubscribe: {e!r}")
            return

        for token in instrument_tokens:
            self.subscribed_tokens.pop(token)

        self.log.info(f"Unsubscribed {len(instrument_tokens)} scripts")

    async def set_mode(
        self, mode: str, instrument_tokens: Union[List[int], Tuple[int]]
    ):
        """
        Set streaming mode for the given list of tokens.

        :param mode: Mode to set. It can be one of `ltp`, `quote`, or `full`
        :type mode: str
        :param instrument_tokens: A collection of instrument tokens
        :type instrument_tokens: List[int] | Tuple[int]
        """
        try:
            await self.ws.send_json(dict(a="mode", v=[mode, instrument_tokens]))
        except Exception as e:
            await self._close(code=0, reason=f"Error while setting mode: {e!r}")
            return

        # Update modes
        for token in instrument_tokens:
            self.subscribed_tokens[token] = mode

        self.log.info(
            f"Steaming mode for {len(instrument_tokens)} scripts set to `{mode}`"
        )

    def _parse_binary(self, bin) -> List[Dict]:
        packets = self._split_packets(bin)
        data = []

        for packet in packets:
            tick = None
            packet_len = len(packet)

            security_id = self._unpack_int(packet, 0, 4)

            # Retrive segment constant from instrument_token
            segment = security_id & 0xFF

            # All indices are not tradable
            tradable = False if segment == self.EXCH_MAP["indices"] else True

            # Add price divisor based on segment
            if segment == self.EXCH_MAP["cds"]:
                divisor = 10000000.0
            elif segment == self.EXCH_MAP["bcd"]:
                divisor = 10000.0
            else:
                divisor = 100.0

            # LTP
            if packet_len == 8:
                tick = dict(
                    tradable=tradable,
                    mode=self.MODE_LTP,
                    instrument_token=security_id,
                    last_price=struct.unpack(">I", packet[4:8])[0] / divisor,
                )
            elif packet_len == 28 or packet_len == 32:
                ltp, high, low, _open, close, change = struct.unpack(
                    ">IIIIII", packet[4:28]
                )

                ltp = ltp / divisor
                close = close / divisor

                tick = dict(
                    tradable=tradable,
                    mode=mode,
                    instrument_token=security_id,
                    last_price=ltp,
                    ohlc=dict(
                        high=high / divisor,
                        low=low / divisor,
                        open=_open / divisor,
                        close=close,
                    ),
                    change=0 if close == 0 else (ltp - close) * 100 / close,
                )

                if packet_len == 32:
                    try:
                        tick["exchange_timestamp"] = datetime.fromtimestamp(
                            self._unpack_int(packet, 28, 32)
                        )
                    except Exception:
                        tick["exchange_timestamp"] = None

            elif packet_len == 44 or packet_len == 184:
                mode = self.MODE_QUOTE if packet_len == 44 else self.MODE_FULL

                (
                    ltp,
                    ltq,
                    atp,
                    vol,
                    buy_qty,
                    sell_qty,
                    _open,
                    high,
                    low,
                    close,
                ) = struct.unpack(">IIIIIIIIII", bin[4:44])

                close = close / divisor
                ltp = ltp / divisor

                tick = dict(
                    tradable=tradable,
                    mode=mode,
                    instrument_token=security_id,
                    last_price=ltp,
                    last_traded_quantity=ltq,
                    average_traded_price=atp / divisor,
                    volume_traded=vol,
                    total_buy_quantity=buy_qty,
                    total_sell_quantity=sell_qty,
                    change=0 if close == 0 else (ltp - close) * 100 / close,
                    ohlc=dict(
                        open=_open / divisor,
                        high=high / divisor,
                        low=low / divisor,
                        close=close,
                    ),
                )

                if packet_len == 184:
                    (
                        ltt,
                        oi,
                        oi_high,
                        oi_low,
                        ts,
                    ) = struct.unpack(">IIIII", bin[44:64])

                    try:
                        ltt = datetime.fromtimestamp(ts)
                    except Exception:
                        ltt = None

                    try:
                        ts = datetime.fromtimestamp(ts)
                    except Exception:
                        ts = None

                    depth = dict(buy=[], sell=[])

                    for i, p in enumerate(range(64, packet_len, 12)):
                        # last 2 bytes are padding, ignore it
                        qty, price, orders = struct.unpack(
                            ">IIH", bin[p : p + 10]
                        )

                        depth["buy" if i < 5 else "sell"].append(
                            dict(
                                quantity=qty,
                                price=price / divisor,
                                orders=orders,
                            )
                        )

                    tick["last_trade_time"] = ltt
                    tick["oi"] = oi
                    tick["oi_day_high"] = oi_high
                    tick["oi_day_low"] = oi_low
                    tick["exchange_timestamp"] = ts
                    tick["depth"] = depth

            data.append(tick)

        return data

    def _parse_text(self, payload) -> None:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")

        try:
            data = json.loads(payload)
        except ValueError:
            return

        msg = data["data"]
        dtype = data["type"]

        # Order update callback
        if dtype == "order" and self.on_order_update:
            self.on_order_update(self, msg)

        if dtype == "error":
            if self.on_error:
                return self.on_error(self, msg)

            self.log.warning(f"Error: {msg}")

        if dtype == "messsage":
            if self.on_message:
                return self.on_message(self, msg)

            self.log.info(f"Message: {msg}")

    def _unpack_int(self, bin, start, end, byte_format="I"):
        """Unpack binary data as unsgined interger."""

        return struct.unpack(">" + byte_format, bin[start:end])[0]

    def _split_packets(self, bin):
        """Split the data to individual packets of ticks.

        Format is <No of Packets><Packet Len><Packet><Packet Len><Packet>...

        https://kite.trade/docs/connect/v3/websocket/#message-structure
        """
        # Ignore heartbeat data.
        if len(bin) < 2:
            return []

        number_of_packets = self._unpack_int(bin, 0, 2, byte_format="H")
        packets = []

        j = 2

        for _ in range(number_of_packets):
            packet_length = self._unpack_int(bin, j, j + 2, byte_format="H")

            end = j + 2 + packet_length

            packets.append(bin[j + 2 : end])

            j = end

        return packets
