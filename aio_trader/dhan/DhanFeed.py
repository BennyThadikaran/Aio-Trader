import asyncio
import struct
from collections import defaultdict
from typing import List, Optional, Tuple

import aiohttp

from aio_trader.utils import configure_default_logger

from ..AbstractFeeder import AbstractFeeder, retry


class DhanFeed(AbstractFeeder):
    """
    Websocket class for Dhan

    Only supports v2 of the API

    .. py:property:: DhanFeed.on_tick
       :type: Callable[[DhanFeed, Dict[str, Any], bool], None]

       A user defined function that receives the tick data as
       a dict and a bool value indicating if the message is parsed.

       def on_tick(feed: DhanFeed, tick: Dict[str, Any], binary=False) -> None

    .. py:property:: DhanFeed.on_connect
       :type: Callable[[DhanFeed, ], None]

       A user defined function called when a websocket connection is opened.

       def on_connect(feed: DhanFeed) -> None

    :param client_id: Dhan client id
    :type client_id: str
    :param access_token: Dhan access token
    :type access_token: str
    :param parse_data: If true, `on_tick` handler receives raw binary/text data. Default True.
    :type parse_data: bool
    :param session: Client Session for making HTTP requests.
    :type session: Optional[aiohttp.ClientSession].

    """

    version = "2"

    WSS_URL = "wss://api-feed.dhan.co"

    # Constants for Exchange Segment
    IDX = 0
    NSE = 1
    NSE_FNO = 2
    NSE_CURR = 3
    BSE = 4
    MCX = 5
    BSE_CURR = 7
    BSE_FNO = 8

    # Constants for Request Code
    Ticker = 15
    Quote = 17
    Depth = 19
    Full = 21

    _disconnect_str_map = {
        "805": "Disconnected: No. of active websocket connections exceeded",
        "806": "Disconnected: Subscribe to Data APIs to continue",
        "807": "Disconnected: Access Token is expired",
        "808": "Disconnected: Invalid Client ID",
        "809": "Disconnected: Authentication Failed - check",
    }

    exchange_map = {
        0: "IDX_I",
        1: "NSE_EQ",
        2: "NSE_FNO",
        3: "NSE_CURRENCY",
        4: "BSE_EQ",
        5: "MCX_COMM",
        7: "BSE_CURRENCY",
        8: "BSE_FNO",
    }

    _dhan_auth = b"\0" * 50

    def __init__(
        self,
        client_id,
        access_token,
        parse_data: bool = True,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        super().__init__()

        self.client_id = client_id
        self.access_token = access_token

        self.parse_data = parse_data
        self.connected = False
        self._shared_session = bool(session)

        self.log = configure_default_logger(__name__)

        self._mode_dct = dict(
            ltp=self.Ticker, quote=self.Quote, full=self.Full, depth=self.Depth
        )

        self._binary_parser_map = {
            "2": self._process_ticker,
            "3": self._process_market_depth,
            "4": self._process_quote,
            "5": self._process_oi,
            "6": self._process_prev_close,
            "7": self._process_status,
            "8": self._process_full,
            "50": self._process_disconnect,
        }

        self.loop = asyncio.get_running_loop()

        if session:
            self.session = session
        else:
            self._initialise_session()

    async def close(self):
        """Perform clean up operations to gracefully exit"""

        if self.connected and hasattr(self, "ws") and not self.ws.closed:
            feed_request_code = 12
            message_length = 83

            await self.ws.send_json(dict(RequestCode=feed_request_code))

            header = struct.pack(
                "<bH30s50s",
                feed_request_code,
                message_length,
                self.client_id.encode("utf-8"),
                self._dhan_auth,
            )

            await self.ws.send_bytes(header)

            await self.ws.close()

        self.log.info("WS Connection closed")
        self.connected = False

        # Dont close the ClientSession, if it was initialized outside the class
        if self._shared_session:
            return

        if self.session and not self.session.closed:
            await self.session.close()

    @retry(max_retries=5, base_wait=2, max_wait=60)
    async def connect(self, **kwargs) -> None:
        """Connect and start the Websocket connection

        Uses the retry decorator. Reconnects in case of error
        @retry(max_retries=5, base_wait=2, max_wait=60)

        :param kwargs: Any keyword arguments to pass to `aiohttp.ClientSession.ws_connect`
        :type: kwargs: Any
        """

        self.ws = await self.session.ws_connect(
            f"{self.WSS_URL}?version={self.version}&token={self.access_token}&clientId={self.client_id}&authType=2",
            heartbeat=self.ping_interval,
            **kwargs,
        )

        if self.ws.closed:
            self.log.warning("Connection failed")
            return

        self.connected = True

        if self.on_connect:
            self.on_connect(self)

        async for msg in self.ws:
            if not self.parse_data:
                return self.on_tick(self, msg.data, binary=True)

            first_byte = struct.unpack("<B", msg.data[0:1])[0]

            data = self._binary_parser_map[str(first_byte)](msg.data)

            self.on_tick(self, data, binary=False)

    async def subscribe(
        self,
        symbols: List[Tuple],
    ) -> None:
        """Subscribe to live market feeds.

        :param symbols: List of instruments to subscribe
        :type symbols: List[Tuple]

        Structure for subscribing is (exchange_segment, "security_id", subscription_type)

        .. code:: python

            symbols = [
                (DhanFeed.NSE, "1333", DhanFeed.Ticker),   # Ticker - Ticker Data
                (DhanFeed.NSE, "1333", DhanFeed.Quote),     # Quote - Quote Data
                (DhanFeed.NSE, "1333", DhanFeed.Full),      # Full - Full Packet
                (DhanFeed.NSE, "11915", DhanFeed.Depth),
            ]

        """
        self.subscribed = symbols

        processed = self._validate_and_process_tuples(self.subscribed)

        for instrument_type, groups in processed.items():
            for group in groups:
                message = dict(
                    RequestCode=int(instrument_type),
                    InstrumentCount=len(group),
                    InstrumentList=[
                        dict(
                            ExchangeSegment=self.exchange_map[ex],
                            SecurityId=token,
                        )
                        for ex, token in group
                    ],
                )

                await self.ws.send_json(message)

        self.log.info(f"Subscribed to {len(self.subscribed)} instruments")

    def subscribe_symbols(self, symbols: List[Tuple]):
        """Function to subscribe to additional symbols when connection is already established.

        :param symbols: List of instruments to subscribe
        :type symbols: List[Tuple]

        Structure for subscribing is (exchange_segment, "security_id", subscription_type)

        .. code:: python

            instruments = [
                (DhanFeed.NSE, "1333", DhanFeed.Ticker),   # Ticker - Ticker Data
                (DhanFeed.NSE, "1333", DhanFeed.Quote),     # Quote - Quote Data
                (DhanFeed.NSE, "1333", DhanFeed.Full),      # Full - Full Packet
                (DhanFeed.NSE, "11915", DhanFeed.Depth),
            ]
        """

        self.subscribed = list(set(self.subscribed).difference(symbols))

        processed = self._validate_and_process_tuples(self.subscribed)

        for instrument_type, groups in processed.items():
            for group in groups:
                message = dict(
                    RequestCode=int(instrument_type),
                    InstrumentCount=len(group),
                    InstrumentList=[
                        dict(
                            ExchangeSegment=self.exchange_map[ex],
                            SecurityId=token,
                        )
                        for ex, token in group
                    ],
                )

                asyncio.create_task(self.ws.send_json(message))

    async def unsubscribe_symbols(
        self,
        symbols: List[Tuple],
    ) -> None:
        """
        Unsubscribe from live market feed.

        .. code:: python

            instruments = [
                (DhanFeed.NSE, "1333", DhanFeed.Ticker),   # Ticker - Ticker Data
                (DhanFeed.NSE, "1333", DhanFeed.Quote),     # Quote - Quote Data
                (DhanFeed.NSE, "1333", DhanFeed.Full),      # Full - Full Packet
                (DhanFeed.NSE, "11915", DhanFeed.Depth),
            ]
        """

        self.subscribed = list(set(self.subscribed).difference(symbols))

        instruments = self._validate_and_process_tuples(self.subscribed)

        for _type, groups in instruments.items():
            for group in groups:
                message = dict(
                    RequestCode=int(_type) + 1,
                    InstrumentCount=len(group),
                    InstrumentList=[
                        dict(
                            ExchangeSegment=self.exchange_map[ex],
                            SecurityId=token,
                        )
                        for ex, token in group
                    ],
                )

                asyncio.create_task(self.ws.send_json(message))

    async def _close(self, code=None, reason=None):
        self.log.error(f"{code}: {reason}")

        await self.close()

    def _process_ticker(self, bin) -> dict:
        *_, segment, id, ltp, ltt = struct.unpack("<BHBIfI", bin[0:16])

        return dict(
            type="Ticker Data",
            exchange_segment=segment,
            security_id=id,
            LTP=round(ltp, 2),
            LTT=ltt,
        )

    def _process_full(self, bin):
        full = struct.unpack("<BHBIfHIfIIIIIIffff100s", bin[0:162])

        packet_format = "<IIHHff"
        market_depth = full[18]
        packet_size = struct.calcsize(packet_format)

        depth = []

        for i in range(5):
            start = i * packet_size
            end = start + packet_size

            packet = struct.unpack(
                packet_format,
                market_depth[start:end],
            )

            depth.append(
                dict(
                    bid_quantity=packet[0],
                    ask_quantity=packet[1],
                    bid_orders=packet[2],
                    ask_orders=packet[3],
                    bid_price=packet[4],
                    ask_price=packet[5],
                )
            )

        return dict(
            type="Full Data",
            exchange_segment=full[2],
            security_id=full[3],
            LTP=round(full[4], 2),
            LTQ=full[5],
            LTT=full[6],
            avg_price=round(full[7], 2),
            volume=full[8],
            total_sell_quantity=full[9],
            total_buy_quantity=full[10],
            OI=full[11],
            oi_day_high=full[12],
            oi_day_low=full[13],
            open=round(full[14], 2),
            close=round(full[15], 2),
            high=round(full[16], 2),
            low=round(full[17], 2),
            depth=depth,
        )

    def _process_market_depth(self, bin):
        *_, segment, id, ltp, depth_bin = struct.unpack(
            "<BHBIf100s", bin[0:112]
        )

        packet_format = "<IIHHff"
        depth = []
        packet_size = struct.calcsize(packet_format)

        for i in range(5):
            start = i * packet_size
            end = start + packet_size

            packet = struct.unpack(packet_format, depth_bin[start:end])

            depth.append(
                dict(
                    bid_quantity=packet[0],
                    ask_quantity=packet[1],
                    bid_orders=packet[2],
                    ask_orders=packet[3],
                    bid_price=packet[4],
                    ask_price=packet[5],
                )
            )

        return dict(
            type="Market Depth",
            exchange_segment=segment,
            security_id=id,
            LTP=ltp,
            depth=depth,
        )

    def _process_quote(self, bin):
        quote = struct.unpack("<BHBIfHIfIIIffff", bin[0:50])

        return dict(
            type="Quote Data",
            exchange_segment=quote[2],
            security_id=quote[3],
            LTP=round(quote[4], 2),
            LTQ=round(quote[5], 2),
            LTT=quote[6],
            avg_price=round(quote[7], 2),
            volume=quote[8],
            total_sell_quantity=quote[9],
            total_buy_quantity=quote[10],
            open=round(quote[11], 2),
            close=round(quote[12], 2),
            high=round(quote[13], 2),
            low=round(quote[14], 2),
        )

    def _process_oi(self, bin):
        oi = struct.unpack("<BHBII", bin[0:12])

        return dict(
            type="OI Data",
            exchange_segment=oi[2],
            security_id=oi[3],
            OI=oi[4],
        )

    def _process_prev_close(self, bin):
        pclose = struct.unpack("<BHBIfI", bin[0:16])

        return dict(
            type="Previous Close",
            exchange_segment=pclose[2],
            security_id=pclose[3],
            prev_close=round(pclose[4], 2),
            prev_OI=pclose[5],
        )

    def _process_status(self, bin):
        status = struct.unpack("<BHBI", bin[0:8])

        return status[3]

    def _process_disconnect(self, bin):
        code = struct.unpack("<BHBIH", bin[0:10])[4]

        if code in self._disconnect_str_map:
            self.log.warning(self._disconnect_str_map[code])

    @staticmethod
    def _validate_and_process_tuples(
        tuples_list: List[Tuple], batch_size=100
    ) -> dict:
        tuple_lengths = set(len(tup) for tup in tuples_list)

        if len(tuple_lengths) > 1:
            raise ValueError(
                "All tuples must be of same size, either all 2 or all 3."
            )

        processed_tuples = set()

        for tup in tuples_list:
            processed_tuples.add((*tup, 15) if len(tup) == 2 else tup)

        batches = defaultdict(list)

        for tup in list(processed_tuples):
            exch, inst_id, _type = tup

            if _type not in (15, 17, 21):
                raise ValueError(
                    "Invalid request mode for v2. Only Ticker, Quote and Full packet are allowed."
                )

            batches[_type].append((exch, inst_id))

        final_dct = {}

        for _type in (15, 17, 19, 21):
            final_dct[_type] = [
                batches[_type][i : i + batch_size]
                for i in range(0, len(batches[_type]), batch_size)
            ]

        return final_dct
