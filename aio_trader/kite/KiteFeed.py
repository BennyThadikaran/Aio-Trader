import json, aiohttp, struct, asyncio, logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union
from ..AbstractFeeder import AbstractFeeder, retry
from aio_trader.utils import configure_default_logger


class KiteFeed(AbstractFeeder):
    """
    Websocket class for Zerodha Kite

    Implements the AbstractFeeder base class

    :param api_key: KiteConnect api_key. Default is "kitefront" for Web login.
    :type api_key: str
    :param user_id: Optional user_id for Kite Web login.
    :type user_id: Optional[str]
    :param enctoken: Optional enctoken for Kite Web login.
    :type enctoken: Optional[str]
    :param access_token: Optional KiteConnect access_token.
    :type access_token: Optional[str]
    :param parse_data: Flag indicating whether to parse Websocket data. Default True.
    :type parse_data: bool
    :param session: Optional aiohttp.ClientSession for making HTTP requests.
    :type session: Optional[aiohttp.ClientSession].
    :param logger: Optional logger instance for logging.
    :type logger: Optional[logging.Logger]
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
        logger: Optional[logging.Logger] = None,
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

        self.log = logger if logger else configure_default_logger(__name__)

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

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()
        return False

    async def close(self):
        """Perform clean up operations"""

        if hasattr(self, "ws"):
            if not self.ws.closed:

                if self.subscribed:
                    await self.unsubscribe_symbols(list(self.subscribed.keys()))

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
    async def connect(self, **kwargs):
        """Connect and start the Websocket connection

        :param **kwargs: Any additional keyword arguments to pass to
            aiohttp.ClientSession.ws_connect
        """

        self.ws = await self.session.ws_connect(
            self.WSS_URL,
            heartbeat=self.ping_interval,
            params=self.auth_params,
            **kwargs,
        )

        self.connected = not self.ws.closed

        if self.on_connect:
            self.on_connect(self)

        async for msg in self.ws:
            # Ignore heartbeat pings
            if len(msg.data) == 1 or not self.on_tick:
                continue

            is_binary = msg.type == aiohttp.WSMsgType.BINARY

            if not self.parse_data:
                self.on_tick(msg.data, binary=is_binary)
                continue

            fn = self._parse_binary if is_binary else self._parse_text

            data = fn(msg.data)

            if data:
                self.on_tick(data, binary=is_binary)

        await self.close()

    async def subscribe_symbols(
        self,
        symbols: Union[List[int], Tuple[int]],
        mode: str = "quote",
    ):
        try:
            await self.ws.send_str(
                json.dumps(dict(a="mode", v=[mode, symbols]))
            )

            for i in symbols:
                self.subscribed[i] = mode

            self.log.info(f"Subscribed: {symbols}")
        except Exception as e:
            await self._close(code=0, reason=f"Error while setting mode: {e}")

    async def unsubscribe_symbols(self, symbols: List[int]):
        try:
            await self.ws.send_str(json.dumps(dict(a="unsubscribe", v=symbols)))

            for i in symbols:
                self.subscribed.pop(i)
            self.log.info(f"Unsubscribed: {symbols}")
        except Exception as e:
            await self._close(code=0, reason=f"Error while unsubscribe: {e}")

    def _parse_binary(self, bin) -> List[Dict]:
        packets = self._split_packets(bin)
        data = []

        for packet in packets:
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
                ltp = self._unpack_int(packet, 4, 8) / divisor

                data.append(
                    dict(
                        tradable=tradable,
                        mode="ltp",
                        security_id=security_id,
                        ltp=ltp,
                    )
                )
            elif packet_len == 28 or packet_len == 32:
                ltp, high, low, _open, close, change = struct.unpack(
                    ">IIIIII", packet[4:28]
                )

                close = close / divisor
                ltp = ltp / divisor

                change = 0 if close == 0 else (ltp - close) * 100 / close

                tick = dict(
                    tradable=tradable,
                    mode="quote",
                    security_id=security_id,
                    ltp=ltp,
                    high=high / divisor,
                    low=low / divisor,
                    open=_open / divisor,
                    close=close,
                    change=change,
                )

                if packet_len == 32:
                    try:
                        tick["ts"] = datetime.fromtimestamp(
                            self._unpack_int(packet, 28, 32)
                        )
                    except Exception:
                        tick["ts"] = None

                data.append(tick)
            elif packet_len >= 44:
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

                change = 0 if close == 0 else (ltp - close) * 100 / close

                tick = dict(
                    tradable=tradable,
                    mode="quote",
                    security_id=security_id,
                    ltp=ltp,
                    ltq=ltq,
                    atp=atp / divisor,
                    volume=vol,
                    buy_qty=buy_qty,
                    sell_qty=sell_qty,
                    open=_open / divisor,
                    high=high / divisor,
                    low=low / divisor,
                    close=close,
                    change=change,
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
                            dict(qty=qty, price=price / divisor, orders=orders)
                        )

                    tick.update(
                        dict(
                            ltt=ltt,
                            oi=oi,
                            oi_high=oi_high,
                            oi_low=oi_low,
                            ts=ts,
                            depth=depth,
                        )
                    )

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
            self.on_order_update(msg)

        if dtype == "error":
            if self.on_error:
                return self.on_error(self, msg)

            self.log.warn(f"Error: {msg}")

        if dtype == "messsage":
            if self.on_message:
                return self.on_message(msg)

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
