import asyncio
import base64
import json
import struct
import time
from typing import List, Literal, Optional, Tuple

import aiohttp

from aio_trader.utils import configure_default_logger

from ..AbstractFeeder import AbstractFeeder, retry
from . import maps

SUBSCRIBE_FAIL = "subscription failed"
SUBS_ERROR_CODE = 11011

UNSUBS_ERROR_CODE = 11012
UNSUBSCRIBE_FAIL = "unsubscription failed"

MODE_ERROR_CODE = 12001
MODE_CHANGE_ERROR = "Mode change failed"

INVALID_CODE = -300
INVALID_SYMBOLS = "Please provide a valid symbol"

CHANNEL_CHANGE_FAIL = "Mode change failed"
RESUME_ERROR_CODE = 11031
PAUSE_ERROR_CODE = 11032

LIMIT_EXCEED_CODE = -99
LIMIT_EXCEED_MSG_5000 = "Please provide less than 5000 symbols"

TOKEN_EXPIRED = -99
TOKEN_EXPIRED_MSG = "Token is expired"
INVALID_TOKEN = "Please provide valid token"

INDEX_DEPTH_ERROR_MESSAGE = "Index does not have market depth"


class SymbolConversion:
    def __init__(
        self, access_token: str, data_type: str, session: aiohttp.ClientSession
    ):
        """
        Initializes a SymbolConversion instance.

        Args:
            access_token (str): The access token used for authentication.
            data_type (str): The data_type associated with the symbol conversion.
                            Valid values are 'Symbolupdate' or 'DepthUpdate'.

        """
        if ":" in access_token:
            access_token = access_token.split(":")[1]

        self.data_type = data_type
        self.access_token = access_token
        self.symbols_token_api = "https://api-t1.fyers.in/data/symbol-token"
        self.session = session

    async def symbol_to_hsmtoken(self, symbols: list) -> Optional[Tuple]:
        """
        Converts symbols to HSM tokens.

        Args:
            symbols (list): A list of symbols to be converted.

        Returns:
            tuple: A tuple containing dictionary and list.
                - The first dictionary represents the mapping of symbols to HSM tokens.
                - The second list represents any symbols that could not be converted.

        """
        data = {"symbols": symbols}

        response = await self.session.post(
            self.symbols_token_api,
            headers={
                "Authorization": self.access_token,
                "Content-Type": "application/json",
            },
            json=data,
        )

        data = await response.json()

        datadict = {}
        wrong_symbol = []
        dp_index_flag = False

        if data["s"] == "ok":
            for symbol, fytoken in data["validSymbol"].items():
                ex_sg = fytoken[:4]

                if ex_sg not in maps.exch_seg_dict:
                    continue

                segment = maps.exch_seg_dict[ex_sg]
                symbol_split = symbol.split("-")
                update_dict = True
                hsm_symbol = None

                if (
                    len(symbol_split) > 1
                    and symbol_split[-1] == "INDEX"
                    and self.data_type != "DepthUpdate"
                ):
                    if symbol in maps.index_dict:
                        exch_token = maps.index_dict[symbol]
                    else:
                        exch_token = symbol.split(":")[1].split("-")[0]

                    hsm_symbol = "if" + "|" + segment + "|" + exch_token
                elif (
                    self.data_type == "DepthUpdate"
                    and symbol_split[-1] != "INDEX"
                ):
                    exch_token = fytoken[10:]
                    hsm_symbol = f"dp|{segment}|{exch_token}"
                elif self.data_type == "SymbolUpdate":
                    exch_token = fytoken[10:]
                    hsm_symbol = f"sf|{segment}|{exch_token}"
                elif (
                    self.data_type == "DepthUpdate"
                    and symbol_split[-1] == "INDEX"
                ):
                    update_dict = False
                    dp_index_flag = True

                if update_dict:
                    datadict[hsm_symbol] = symbol

            if data["invalidSymbol"]:
                wrong_symbol = data["invalidSymbol"]

            return (datadict, wrong_symbol, dp_index_flag, "")

        elif data["s"] == "error":

            return ({}, [], dp_index_flag, data["message"])


class FyersFeed(AbstractFeeder):
    """
    Websocket class for Fyers

    .. py:property:: FyersFeed.on_tick
       :type: Callable[[FyersFeed, Dict[str, Any], bool], None]

       A user defined function called, when tick data is received.
       It receives the dictionary and a bool value indicating if the
       tick data is parsed.

       def on_tick(feed: FyersFeed, tick: dict, binary=False) -> None

    .. py:property:: FyersFeed.on_connect
       :type: Callable[[FyersFeed], None]

       A user defined function called, when a websocket connection is established

       def on_connect(feed: FyersFeed) -> None

    .. py:property:: FyersFeed.on_error
       :type: Callable[[FyersFeed, error: Dict[str, Any]], None]

       A user defined function called, when an error occurs

       **Error dictionary has the following key values:**

       - code: int - Error code
       - message: str - The error message

       def on_error(feed: FyersFeed, error: dict) -> None

    :param access_token: Fyers `access_token`.
    :type access_token: str
    :param litemode: If true, only last traded price is updated in the feed. Default True.
    :type litemode: bool
    :param parse_data: If true, `on_tick` handler receives raw binary/text data. Default True.
    :type parse_data: bool
    :param session: Client Session for making HTTP requests.
    :type session: Optional[aiohttp.ClientSession].
    """

    WSS_URL = "wss://socket.fyers.in/hsm/v1-5/prod"

    def __init__(
        self,
        access_token: str,
        litemode=False,
        parse_data: bool = True,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        super().__init__()

        self.access_token = access_token
        self.update_tick = False
        self.lite = litemode

        self.parse_data = parse_data
        self.connected = False
        self._shared_session = bool(session)

        self.log = configure_default_logger(__name__)

        self.loop = asyncio.get_running_loop()

        if session:
            self.session = session
        else:
            self._initialise_session()

        self.update_count = 0

        self.resp = {}
        self.dp_sym = {}
        self.index_sym = {}
        self.symbol_token = {}
        self.scrips_sym = {}
        self.scrips_count = {}

        self.channel_symbol = []
        self.channel_num = 11
        self.active_channel = None
        self.running_channels = set()
        self.scrips_per_channel = {i: [] for i in range(1, 30)}

        self.symbol_limit = 5000
        self.source = "PythonSDK-3.0.9"

        self.mode = "P"

        self.__binary_parser_map = {
            "1": self.__auth_resp,
            "4": self.__subscribe_resp,
            "5": self.__unsubscribe_resp,
            "6": self.__datafeed_resp,
            "7": self.__resume_pause_resp,
            "12": self.__lite_full_mode_resp,
        }

    async def close(self):
        """Perform clean up operations to gracefully exit"""

        if self.connected and hasattr(self, "ws") and not self.ws.closed:
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

        Uses the retry decorator to reconnect on error

        @retry(max_retries=5, base_wait=2, max_wait=60)

        :param kwargs: Any keyword arguments to pass to `aiohttp.ClientSession.ws_connect`
        :type: kwargs: Any
        """

        if self.__access_token_to_hsmtoken() and self._valid_token:
            self.ws = await self.session.ws_connect(
                self.WSS_URL,
                heartbeat=self.ping_interval,
                **kwargs,
            )

        if self.ws.closed:
            self.log.warning("Connection failed")
            return

        self.connected = True

        await self.ws.send_bytes(self.__access_token_msg())

        if self.lite:
            message = self.__lite_mode_msg()
        else:
            message = self.__full_mode_msg()

        await self.ws.send_bytes(message)

        if self.on_connect:
            self.on_connect(self)

        async for msg in self.ws:
            if not self.parse_data:
                return self.on_tick(self, msg.data, binary=True)

            _, resp_type = struct.unpack("!HB", msg.data[:3])

            resp_type = str(resp_type)

            if resp_type in self.__binary_parser_map:
                self.__binary_parser_map[resp_type](msg.data)

    async def unsubscribe(
        self,
        symbols: List[str],
        data_type: Literal["SymbolUpdate", "DepthUpdate"]= "SymbolUpdate",
        channel: int = 11,
    ):
        """
        Unsubscribes from real-time data updates for the specified symbols.

        symbols = ['NSE:SBIN-EQ', 'NSE:ADANIENT-EQ']

        :param symbols: A list of symbols to unsubscribe from.
        :type symbols: List[str]
        :param data_type: Default "SymbolUpdate". The type of data to unsubscribe from.
        :type symbols: Literal["SymbolUpdate", "DepthUpdate"]
        :param channel: Default 11. The channel to use for unsubscription.
        :type channel: int
        """
        if not self._valid_token:
            return

        self.data_type = data_type
        self.symbols = symbols
        self.channel_num = channel
        self.__channel_resume_pause()
        self.channel_symbol = await self.__symbol_conversion(symbols)

        if self.channel_symbol is None:
            return

        self.unsub_symbol = list(self.channel_symbol.keys())

        for sym in self.unsub_symbol:
            if sym not in self.scrips_count[self.channel_num]:
                self.unsub_symbol.remove(sym)

        if len(self.unsub_symbol) != 0:
            total_symbols = len(self.unsub_symbol)
            symbol_chunks = [
                self.unsub_symbol[i : i + 1500]
                for i in range(0, total_symbols, 1500)
            ]
            for symbols in symbol_chunks:
                message = self.__unsubscription_msg(symbols)
                await self.ws.send_bytes(message)
        else:
            self.log.warning(INVALID_SYMBOLS)

            if self.on_error:
                self.on_error(
                    self,
                    dict(
                        code=INVALID_CODE,
                        message=INVALID_SYMBOLS
                    ),
                )

    async def subscribe(
        self,
        symbols: List[str],
        data_type: Literal['SymbolUpdate', "DepthUpdate"]= "SymbolUpdate",
        channel: int = 11,
    ):
        """
        Subscribes to real-time data updates for the specified symbols.

        symbols = ['NSE:SBIN-EQ', 'NSE:ADANIENT-EQ']

        :param symbols: A list of symbols to subscribe.
        :type symbols: List[str]
        :param data_type: Default "SymbolUpdate". The type of data to subscribe.
        :type data_type: Literal['SymbolUpdate', "DepthUpdate"]
        :param channel: Default 11. The channel to use for subscription. 
        :type channel: int

        """
        if not self._valid_token:
            return

        self.data_type = data_type
        self.symbols = symbols
        self.channel_num = channel
        self.__channel_resume_pause()
        self.channel_symbol = await self.__symbol_conversion(symbols)

        if self.channel_symbol is None:
            return

        if len(self.symbol_token) + len(self.channel_symbol) > 5000:
            self.log.warning(LIMIT_EXCEED_MSG_5000)

            if self.on_error:
                self.on_error(
                    self,
                    dict(
                        code=LIMIT_EXCEED_CODE,
                        message=LIMIT_EXCEED_MSG_5000
                    ),
                )
            return

        self.symbol_token.update(self.channel_symbol)

        self.scrips_count[self.channel_num] = list(self.channel_symbol.keys())

        total_symbols = len(self.scrips_count[self.channel_num])

        symbol_chunks = [
            self.scrips_count[self.channel_num][i : i + 1500]
            for i in range(0, total_symbols, 1500)
        ]

        for symbols in symbol_chunks:
            message = self.__subscription_msg(symbols)
            await asyncio.sleep(0.5)
            await self.ws.send_bytes(message)

    def channel_resume(self, channel: int) -> None:
        """
        Resumes the specified channel.

        :param channel: The channel number to resume.
        :type channel: int
        """
        self.channel_num = channel
        self.__channel_resume_pause()

    def __access_token_to_hsmtoken(self) -> bool:
        """
        Decode APIv2 token to extract 'hsm_key' and check for validity.

        This function decodes the APIv2 access token and extracts the 'hsm_key' from it.
        It also verifies if the token is expired by comparing the 'exp' (expiration) claim in the
        token's payload with the current timestamp. If the token is valid and not expired, it sets
        the 'hsm_token' attribute and returns True. Otherwise, it raises an error and returns False.

        Returns:
            bool: True if the token is valid and not expired, False otherwise.
        """
        try:
            header_token, payload_b64, _ = self.access_token.split(".")

            # Decode the base64 encoded payload
            _ = base64.urlsafe_b64decode(header_token + "===")
            decoded_payload = base64.urlsafe_b64decode(payload_b64 + "===")

            # Convert the decoded payload to a string (assuming it's in JSON format)
            decode_token = json.loads(decoded_payload.decode())

            today = int(time.time())

            if decode_token["exp"] - today < 0:
                self.log.warning(TOKEN_EXPIRED_MSG)

                if self.on_error:
                    self.on_error(
                        self,
                        dict(
                            code=TOKEN_EXPIRED,
                            message=TOKEN_EXPIRED_MSG
                        ),
                    )
                return False

            self._valid_token = True

            self.__hsm_token = decode_token["hsm_key"]
        except:
            self.log.warning(INVALID_TOKEN)

            if self.on_error:
                self.on_error(
                    self,
                    dict(
                        code=INVALID_CODE,
                        message=INVALID_TOKEN,
                    ),
                )

            return False

        return True

    

    def __auth_resp(self, data: bytearray):
        """
        Unpacks the authentication response from a bytearray.

        Args:
            data (bytearray): The authentication response message.

        Returns:
            dict: The authentication response as a dictionary with keys 'code', 'message', and 's'.
        """
        field_length = struct.unpack("!H", data[5:7])[0]
        string_val = data[7 : 7 + field_length].decode("utf-8")

        if string_val == "K":
            self.log.info("Authentication done")
        else:
            self.log.warning("Authentication failed")
            self.loop.create_task(self.close())

        offset = 7 + field_length + 1
        field_length = struct.unpack("!H", data[offset : offset + 2])[0]

        offset += 2
        self.ack_count = struct.unpack(">I", data[offset : offset + 4])[0]

    def __subscribe_resp(self, data: bytearray):
        """
        Unpacks the subscription response from a bytearray.

        Args:
            data (bytearray): The subscription response message.

        Returns:
            dict: The subscription response as a dictionary with keys 'code', 'message', and 's'.
        """
        string_val = data[7:8].decode("latin-1")

        if string_val == "K":
            self.log.info("Subscribed")
        else:
            self.log.warning(SUBSCRIBE_FAIL)

            if self.on_error:
                self.on_error(
                    self,
                    dict(
                        code=SUBS_ERROR_CODE,
                        message=SUBSCRIBE_FAIL
                    ),
                )

    def __unsubscribe_resp(self, data: bytearray):
        """
        Unpacks the unsubscription response from a bytearray.

        Args:
            data (bytearray): The unsubscription response message.

        Returns:
            dict: The unsubscription response as a dictionary with keys 'code', 'message', and 's'.
        """

        offset = 5
        field_length = struct.unpack("H", data[offset : offset + 2])[0]

        offset += 2

        string_val = data[offset : offset + 1].decode("latin-1")

        offset += field_length

        if string_val == "K":

            self.log.info("Unsubscribed")

            for symbol in self.unsub_symbol:
                count = 0
                for channel in self.running_channels:
                    if symbol in self.scrips_per_channel[channel]:
                        count += 1
                    if count > 1:
                        break

                assert self.active_channel is not None

                if symbol in self.scrips_per_channel[self.active_channel]:
                    self.scrips_per_channel[self.active_channel].remove(symbol)

                if count == 1:
                    self.symbol_token.pop(symbol)

        else:
            self.log.warning(UNSUBSCRIBE_FAIL)

            if self.on_error:
                self.on_error(
                    self,
                    dict(
                        code=UNSUBS_ERROR_CODE,
                        message=UNSUBSCRIBE_FAIL,
                    ),
                )

    def __datafeed_resp(self, data: bytearray):
        """
        Unpacks and processes the data based on data_type and sends it to the __response_output function.

        Args:
            data (bytearray): The response data.

        Returns:
            None
        """
        if self.ack_count > 0:
            self.update_count += 1

            message_num = struct.unpack(">I", data[3:7])[0]

            if self.update_count == self.ack_count:
                ack_msg = self.__acknowledgement_msg(message_num)
                self.loop.create_task(self.ws.send_bytes(ack_msg))
                self.update_count = 0

        scrip_count = struct.unpack("!H", data[7:9])[0]
        offset = 9

        for _ in range(scrip_count):
            data_type = struct.unpack("B", data[9:10])[0]

            if data_type == 83:  # Snapshot datafeed

                topic_id = struct.unpack("H", data[10:12])[0]
                topic_name_len = struct.unpack("B", data[12:13])[0]
                topic_name = data[13 : 13 + topic_name_len].decode("utf-8")

                offset = 13 + topic_name_len

                # Maintaining dict - topic_id : topic_name
                if topic_name[:2] == "dp":
                    self.dp_sym[topic_id] = topic_name

                    self.resp[self.dp_sym[topic_id]] = {}

                    field_count = struct.unpack("B", data[offset : offset + 1])[
                        0
                    ]
                    offset += 1

                    for index in range(field_count):
                        value = struct.unpack(">i", data[offset : offset + 4])[
                            0
                        ]
                        offset += 4

                        if value != -2147483648:
                            self.resp[self.dp_sym[topic_id]][
                                maps.depth_value[index]
                            ] = value

                    offset += 2

                    multiplier = struct.unpack(">H", data[offset : offset + 2])[
                        0
                    ]

                    self.resp[self.dp_sym[topic_id]]["multiplier"] = multiplier

                    offset += 2

                    precision = struct.unpack("B", data[offset : offset + 1])[0]

                    self.resp[self.dp_sym[topic_id]]["precision"] = precision

                    offset += 1

                    val = ["exchange", "exchange_token", "symbol"]

                    for i in range(3):
                        string_len = struct.unpack(
                            "B", data[offset : offset + 1]
                        )[0]

                        offset += 1

                        string_data = data[offset : offset + string_len].decode(
                            "utf-8", errors="ignore"
                        )

                        self.resp[self.dp_sym[topic_id]][val[i]] = string_data

                        offset += string_len

                    self.resp[self.dp_sym[topic_id]]["type"] = "dp"

                    self.resp[topic_name]["symbol"] = self.symbol_token[
                        topic_name
                    ]

                    self.__response_output(
                        self.resp[self.dp_sym[topic_id]], "depth"
                    )

                elif topic_name[:2] == "if":

                    self.index_sym[topic_id] = topic_name
                    self.resp[self.index_sym[topic_id]] = {}

                    # field_count - 21 in scrips , 25 in depth , 6 in index
                    field_count = struct.unpack("B", data[offset : offset + 1])[
                        0
                    ]
                    offset += 1

                    for index in range(field_count):

                        value = struct.unpack(">i", data[offset : offset + 4])[
                            0
                        ]
                        offset += 4

                        if value != -2147483648:
                            self.resp[self.index_sym[topic_id]][
                                maps.index_val[index]
                            ] = value

                    offset += 2

                    multiplier = struct.unpack(">H", data[offset : offset + 2])[
                        0
                    ]

                    self.resp[self.index_sym[topic_id]][
                        "multiplier"
                    ] = multiplier

                    offset += 2

                    precision = struct.unpack("B", data[offset : offset + 1])[0]

                    self.resp[self.index_sym[topic_id]]["precision"] = precision

                    offset += 1

                    val = ["exchange", "exchange_token", "symbol"]

                    for i in range(3):
                        string_len = struct.unpack(
                            "B", data[offset : offset + 1]
                        )[0]

                        offset += 1

                        string_data = data[offset : offset + string_len].decode(
                            "utf-8", errors="ignore"
                        )

                        self.resp[self.index_sym[topic_id]][
                            val[i]
                        ] = string_data

                        offset += string_len

                    self.resp[topic_name]["symbol"] = self.symbol_token[
                        topic_name
                    ]

                    self.resp[self.index_sym[topic_id]]["type"] = "if"

                    self.__response_output(
                        self.resp[self.index_sym[topic_id]], "index"
                    )

                elif topic_name[:2] == "sf":
                    self.scrips_sym[topic_id] = topic_name

                    self.resp[self.scrips_sym[topic_id]] = {}

                    # field_count - 21 in scrips , 25 in depth , 6 in index
                    field_count = struct.unpack("B", data[offset : offset + 1])[
                        0
                    ]

                    offset += 1

                    for index in range(field_count):
                        value = struct.unpack(">i", data[offset : offset + 4])[
                            0
                        ]

                        offset += 4

                        if value != -2147483648:
                            self.resp[self.scrips_sym[topic_id]][
                                maps.data_val[index]
                            ] = value

                    offset += 2

                    multiplier = struct.unpack(">H", data[offset : offset + 2])[
                        0
                    ]

                    self.resp[self.scrips_sym[topic_id]][
                        "multiplier"
                    ] = multiplier

                    offset += 2

                    precision = struct.unpack("B", data[offset : offset + 1])[0]

                    self.resp[self.scrips_sym[topic_id]][
                        "precision"
                    ] = precision

                    offset += 1

                    val = ["exchange", "exchange_token", "symbol"]

                    for i in range(3):
                        string_len = struct.unpack(
                            "B", data[offset : offset + 1]
                        )[0]

                        offset += 1

                        string_data = bytes(
                            data[offset : offset + string_len]
                        ).decode("utf-8", errors="ignore")

                        self.resp[self.scrips_sym[topic_id]][
                            val[i]
                        ] = string_data

                        offset += string_len

                    self.resp[topic_name]["symbol"] = self.symbol_token[
                        topic_name
                    ]

                    self.resp[self.scrips_sym[topic_id]]["type"] = "sf"

                    self.__response_output(
                        self.resp[self.scrips_sym[topic_id]], "scrips"
                    )

            elif data_type == 85:  # Full mode datafeed
                offset += 1

                topic_id = struct.unpack("H", data[offset : offset + 2])[0]

                offset += 2

                field_count = struct.unpack("B", data[offset : offset + 1])[0]

                offset += 1

                sf_flag, idx_flag, dp_flag = False, False, False

                self.update_tick = False

                for index in range(field_count):
                    value = struct.unpack(">i", data[offset : offset + 4])[0]

                    offset += 4

                    # if field_count == 20 or field_count == 21:
                    if topic_id in self.scrips_sym:
                        if (
                            maps.data_val[index]
                            in self.resp[self.scrips_sym[topic_id]]
                            and self.resp[self.scrips_sym[topic_id]][
                                maps.data_val[index]
                            ]
                            != value
                            and value != -2147483648
                        ):
                            self.resp[self.scrips_sym[topic_id]][
                                maps.data_val[index]
                            ] = value

                            self.update_tick = True
                        elif (
                            maps.data_val[index]
                            not in self.resp[self.scrips_sym[topic_id]]
                            and value != -2147483648
                        ):
                            self.resp[self.scrips_sym[topic_id]][
                                maps.data_val[index]
                            ] = value
                            self.update_tick = True

                        sf_flag = True
                    elif topic_id in self.index_sym:
                        if (
                            maps.index_val[index]
                            in self.resp[self.index_sym[topic_id]]
                            and self.resp[self.index_sym[topic_id]][
                                maps.index_val[index]
                            ]
                            != value
                            and value != "-2147483648"
                        ):

                            self.resp[self.index_sym[topic_id]][
                                maps.index_val[index]
                            ] = value
                            self.update_tick = True
                        elif (
                            maps.index_val[index]
                            not in self.resp[self.index_sym[topic_id]]
                            and value != -2147483648
                        ):
                            self.resp[self.index_sym[topic_id]][
                                maps.index_val[index]
                            ] = value
                            self.update_tick = True
                        idx_flag = True
                    elif topic_id in self.dp_sym:
                        if (
                            maps.depth_value[index]
                            in self.resp[self.dp_sym[topic_id]]
                            and self.resp[self.dp_sym[topic_id]][
                                maps.depth_value[index]
                            ]
                            != value
                            and value != -2147483648
                        ):
                            self.resp[self.dp_sym[topic_id]][
                                maps.depth_value[index]
                            ] = value
                            self.update_tick = True
                        elif (
                            maps.depth_value[index]
                            not in self.resp[self.dp_sym[topic_id]]
                            and value != -2147483648
                        ):
                            self.resp[self.dp_sym[topic_id]][
                                maps.depth_value[index]
                            ] = value
                            self.update_tick = True
                        dp_flag = True
                if self.update_tick:
                    if sf_flag:
                        self.__response_output(
                            self.resp[self.scrips_sym[topic_id]], "scrips"
                        )
                    elif idx_flag:
                        self.__response_output(
                            self.resp[self.index_sym[topic_id]], "index"
                        )
                    elif dp_flag:
                        self.__response_output(
                            self.resp[self.dp_sym[topic_id]], "depth"
                        )

            elif data_type == 76:  # lite mode datafeed

                offset += 1

                topic_id = struct.unpack("H", data[offset : offset + 2])[0]

                offset += 2

                sf_flag, idx_flag = False, False

                if topic_id in self.scrips_sym:

                    # for index in range(3):
                    value = struct.unpack(">i", data[offset : offset + 4])[0]

                    offset += 4

                    if (
                        value
                        != self.resp[self.scrips_sym[topic_id]][
                            maps.data_val[0]
                        ]
                        and value != -2147483648
                    ):
                        self.resp[self.scrips_sym[topic_id]][
                            maps.data_val[0]
                        ] = value

                        sf_flag = True

                        self.resp[self.scrips_sym[topic_id]]["type"] = "sf"

                        self.__response_output(
                            self.resp[self.scrips_sym[topic_id]], "scrips"
                        )
                elif topic_id in self.index_sym:

                    value = struct.unpack(">i", data[offset : offset + 4])[0]

                    offset += 4

                    if (
                        value
                        != self.resp[self.index_sym[topic_id]][
                            maps.index_val[0]
                        ]
                        and value != -2147483648
                    ):
                        self.resp[self.index_sym[topic_id]][
                            maps.index_val[0]
                        ] = value

                        idx_flag = True

                        self.resp[self.index_sym[topic_id]]["type"] = "if"

                        self.__response_output(
                            self.resp[self.index_sym[topic_id]], "index"
                        )

    def __acknowledgement_msg(self, message_number: int) -> bytearray:
        """
        Create a message in bytearray for acknowledgement.

        Args:
            message_number (int): The message number to acknowledge.

        Returns:
            bytearray: The acknowledgement message in bytearray format.
        """
        total_size = 11
        req_type = 3
        field_count = 1
        field_id = 1
        field_size = 4
        field_value = message_number

        buffer_msg = bytearray()

        # Pack the data into the byte array
        buffer_msg.extend(struct.pack(">H", total_size - 2))
        buffer_msg.extend(struct.pack("B", req_type))
        buffer_msg.extend(struct.pack("B", field_count))
        buffer_msg.extend(struct.pack("B", field_id))
        buffer_msg.extend(struct.pack(">H", field_size))
        buffer_msg.extend(struct.pack(">I", field_value))

        return buffer_msg

    def __response_output(self, data: dict, data_type: str) -> object:
        """
        Processes the response data and returns the output based on the specified data_type.

        Args:
            data (bytearray): The response data.
            data_type (str): The type of data to be processed.

        Returns:
            object: The processed output based on the specified data_type.
        """
        data_resp = data

        precision_calcu_value = [
            "ltp",
            "bid_price",
            "ask_price",
            "avg_trade_price",
            "low_price",
            "high_price",
            "open_price",
            "prev_close_price",
        ]

        response = {}

        if "bidPrice1" not in data_resp and self.lite:
            for i, val in enumerate(maps.lite_val):
                if val in data_resp and val == "ltp":
                    response[val] = data_resp[val] / (
                        (10 ** data_resp["precision"]) * data_resp["multiplier"]
                    )
                else:
                    response[val] = data_resp[val]

            if "prev_close_price" in response and "ltp" in response:
                response["ch"] = round(
                    (response["ltp"] - response["prev_close_price"]), 2
                )

                response["chp"] = round(
                    (response["ch"] / response["prev_close_price"] * 100), 2
                )
        else:
            if data_type == "depth":

                for i, val in enumerate(maps.depth_value):
                    if val in data_resp and i < 10:
                        response[val] = data_resp[val] / (
                            (10 ** data_resp["precision"])
                            * data_resp["multiplier"]
                        )
                    elif val in data_resp:
                        response[val] = data_resp[val]

            elif data_type == "scrips":

                for i, val in enumerate(maps.data_val):
                    if (
                        val in data_resp
                        and val in precision_calcu_value
                        and val not in ["upper_ckt", "lower_ckt"]
                    ):
                        response[val] = data_resp[val] / (
                            (10 ** data_resp["precision"])
                            * data_resp["multiplier"]
                        )

                    elif val in data_resp:
                        response[val] = data_resp[val]

                response["lower_ckt"] = 0

                response["upper_ckt"] = 0

                if (
                    "prev_close_price" in response
                    and "ltp" in response
                    and response["prev_close_price"] != 0
                ):
                    response["ch"] = round(
                        (response["ltp"] - response["prev_close_price"]), 4
                    )

                    response["chp"] = round(
                        (response["ch"] / response["prev_close_price"] * 100), 4
                    )

                if "OI" in response:
                    response.pop("OI")

                if "Yhigh" in response:
                    response.pop("Yhigh")

                if "Ylow" in response:
                    response.pop("Ylow")
            else:
                for i, val in enumerate(maps.index_val):
                    if val in data_resp and i in [0, 1, 3, 4, 5]:
                        response[val] = data_resp[val] / (
                            (10 ** data_resp["precision"])
                            * data_resp["multiplier"]
                        )
                    elif val in data_resp:
                        response[val] = data_resp[val]

                    if "prev_close_price" in response and "ltp" in response:
                        response["ch"] = round(
                            (response["ltp"] - response["prev_close_price"]), 2
                        )
                        response["chp"] = round(
                            (
                                response["ch"]
                                / response["prev_close_price"]
                                * 100
                            ),
                            2,
                        )

        if self.on_tick:
            self.on_tick(self, response, binary=False)

    def __resume_pause_resp(self, data: bytearray, channeltype: int):
        """
        Unpacks and processes the resume/pause response data based on the channel type.

        Args:
            data (bytearray): The response data.
            channeltype (int): The channel type. 7 for pause and 8 for resume.

        Returns:
            dict: The resume/pause response as a dictionary with keys 'code', 'message', and 's'.
        """
        offset = 5

        # Unpack the field length
        field_length = struct.unpack("!H", data[offset : offset + 2])[0]

        offset += 2

        # Extract the string value and decode it
        string_val = data[offset : offset + field_length].decode("utf-8")

        offset += field_length

        if string_val == "K":
            self.log.info(
                "Channel Paused" if channeltype == 7 else "Channel Resumed"
            )
        else:
            self.log.warning(CHANNEL_CHANGE_FAIL)

            if self.on_error:
                if channeltype == 7:
                    self.on_error(
                        self,
                        dict(
                            code=PAUSE_ERROR_CODE,
                            message=CHANNEL_CHANGE_FAIL,
                        ),
                    )
                else:
                    self.on_error(
                        self,
                        dict(
                            code=RESUME_ERROR_CODE,
                            message=CHANNEL_CHANGE_FAIL,
                        ),
                    )

    def __lite_full_mode_resp(self, data: bytearray):
        """
        Unpacks the lite/full mode response from a bytearray.

        Args:
            data (bytearray): The lite/full mode response message.

        Returns:
            dict: The lite/full mode response as a dictionary with keys 'code', 'message', and 's'.
        """

        offset = 3

        # Unpack the field count
        field_count = struct.unpack("!B", data[offset : offset + 1])[0]

        if field_count >= 1:
            # Unpack the field ID
            offset += 2

            # Unpack the field length
            field_length = struct.unpack("!H", data[offset : offset + 2])[0]
            offset += 2

            # Extract the string value and decode it
            string_val = data[offset : offset + field_length].decode("utf-8")
            offset += field_length

            if string_val == "K":
                self.log.info("Lite Mode On" if self.lite else "Full Mode On")
            else:
                self.log.warning(MODE_CHANGE_ERROR)

                if self.on_error:
                    self.on_error(
                        self,
                        dict(code=MODE_ERROR_CODE, message=MODE_CHANGE_ERROR),
                    )

    def __channel_resume_pause(self):
        """
        Pauses the active channel and resumes the specified channel if necessary.

        If the WebSocket object (__ws_object) is not None and there is an active channel (active_channel)
        that is different from the specified channel (channelNum), the function creates and appends a pause message
        for the active channel to the message list. If the specified channel is already in the running_channels set,
        the function creates and appends a resume message for the specified channel to the message list.

        Finally, it updates the running_channels set and sets the active_channel to the specified channel (channelNum).
        """
        if (
            self.ws.closed
            and self.active_channel is not None
            and self.active_channel != self.channel_num
        ):
            message = self.__channel_pause_msg(self.active_channel)

            self.loop.create_task(self.ws.send_bytes(message))

            if self.channel_num in self.running_channels:
                message = self.__channel_resume_msg(self.channel_num)

                self.loop.create_task(self.ws.send_bytes(message))

        self.running_channels.add(self.channel_num)
        self.active_channel = self.channel_num

    def __channel_pause_msg(self, channel: int) -> bytearray:
        """
        Create a message in bytearray for channel pause.

        Args:
            channel (int): The channel to pause.

        Returns:
            bytearray: The channel pause message in bytearray format.
        """
        data = bytearray()

        data.extend(struct.pack(">H", 0))

        data.extend(struct.pack("B", 7))

        data.extend(struct.pack("B", 1))

        channel_bits = 0

        if channel < 64 and channel > 0:
            channel_bits |= 1 << channel

        field = bytearray()
        field.extend(struct.pack("B", 1))
        field.extend(struct.pack(">H", 8))
        field.extend(struct.pack(">Q", channel_bits))
        data.extend(field)

        return data

    def __channel_resume_msg(self, channel: int) -> bytearray:
        """
        Create a message in bytearray for channel resume.

        Args:
            channel (int): The channel to resume.

        Returns:
            bytearray: The channel resume message in bytearray format.
        """
        data = bytearray()

        data.extend(struct.pack(">H", 0))

        data.extend(struct.pack("B", 8))

        data.extend(struct.pack("B", 1))

        channel_bits = 0

        if channel < 64 and channel > 0:
            channel_bits |= 1 << channel

        field = bytearray()
        field.extend(struct.pack("B", 1))
        field.extend(struct.pack(">H", 8))
        field.extend(struct.pack(">Q", channel_bits))
        data.extend(field)

        return data

    async def __symbol_conversion(self, symbolslst: list):
        """
        Converts symbols to HSM symbol tokens and returns a dictionary of {hsmtoken: symbol}.

        Args:
            symbolslst (list): A list of symbols to convert.

        Returns:
            dict: A dictionary mapping HSM symbol tokens to symbols.
        """
        wrong_symbols = []
        symb_flag = False
        idx_dp_flag = False
        symbol_dict = {}
        total_symbols = len(symbolslst)

        if (
            len(self.scrips_per_channel[self.channel_num]) > self.symbol_limit
            or total_symbols > self.symbol_limit
            and len(self.scrips_per_channel[self.channel_num]) + total_symbols
            > self.symbol_limit
        ):
            self.log.warning(LIMIT_EXCEED_MSG_5000)

            if self.on_error:
                self.on_error(
                    self,
                    dict(
                        code=LIMIT_EXCEED_CODE,
                        message=LIMIT_EXCEED_MSG_5000,
                    ),
                )
            return

        symbol_chunks = [
            symbolslst[i : i + 500] for i in range(0, total_symbols, 500)
        ]

        conv = SymbolConversion(self.access_token, self.data_type, self.session)

        for symbols in symbol_chunks:
            symbol_value = await conv.symbol_to_hsmtoken(symbols)

            if symbol_value is None:
                return

            if symbol_value[3] != "":
                self.log.warning(f"Invalid symbol: {symbol_value[3]}")

                if self.on_error:
                    self.on_error(
                        self, dict(code=INVALID_CODE, message=symbol_value[3])
                    )
                return

            symbol_dict.update(symbol_value[0])

            if isinstance(symbol_value[1], list) and len(symbol_value[1]) > 0:
                wrong_symbols += symbol_value[1]
                symb_flag = True

            if symbol_value[2] == True:
                idx_dp_flag = True

        if symb_flag:
            self.log.warning(INVALID_SYMBOLS, wrong_symbols)

            if self.on_error:
                self.on_error(
                    self,
                    dict(
                        code=INVALID_CODE,
                        message=INVALID_SYMBOLS,
                        invalid_symbols=wrong_symbols,
                    ),
                )

        if idx_dp_flag:
            self.log.warning(INDEX_DEPTH_ERROR_MESSAGE)

            if self.on_error:
                self.on_error(
                    self,
                    dict(
                        code=INVALID_CODE,
                        message=INDEX_DEPTH_ERROR_MESSAGE,
                    ),
                )

        return symbol_dict

    def __unsubscription_msg(self, symbols: list) -> bytearray:
        """
        Create a message in bytearray for unsubscription message.

        Args:
            symbols (list): A list of symbols to unsubscribe from.

        Returns:
            bytearray: The unsubscription message in bytearray format.
        """
        scrips_data = bytearray()
        scrips_data.append(len(symbols) >> 8 & 0xFF)
        scrips_data.append(len(symbols) & 0xFF)

        for scrip in symbols:
            scrip_bytes = str(scrip).encode("ascii")
            scrips_data.append(len(scrip_bytes))
            scrips_data.extend(scrip_bytes)

        data_len = (
            18 + len(scrips_data) + len(self.access_token) + len(self.source)
        )

        request_type = 5
        field_count = 2

        buffer_msg = bytearray()
        buffer_msg.extend(struct.pack(">H", data_len))
        buffer_msg.append(request_type)
        buffer_msg.append(field_count)

        # Field-1
        buffer_msg.append(1)
        buffer_msg.extend(struct.pack(">H", len(scrips_data)))
        buffer_msg.extend(scrips_data)

        # Field-2
        buffer_msg.append(2)
        buffer_msg.extend(struct.pack(">H", 1))
        buffer_msg.append(self.channel_num)

        return buffer_msg

    def __subscription_msg(self, symbols: list) -> bytearray:
        """
        Create a message in bytearray for symbol subscription.

        Args:
            symbols (list): A list of symbols to subscribe to.

        Returns:
            bytearray: The subscription message in bytearray format.
        """

        self.scrips_per_channel[self.channel_num] += symbols
        self.scrips = symbols
        self.scrips_data = bytearray()
        self.scrips_data.append(len(self.scrips) >> 8 & 0xFF)
        self.scrips_data.append(len(self.scrips) & 0xFF)

        for scrip in self.scrips:
            scrip_bytes = str(scrip).encode("ascii")
            self.scrips_data.append(len(scrip_bytes))
            self.scrips_data.extend(scrip_bytes)

        data_len = (
            18
            + len(self.scrips_data)
            + len(self.access_token)
            + len(self.source)
        )

        request_type = 4
        field_count = 2

        buffer_msg = bytearray()

        buffer_msg.extend(struct.pack(">H", data_len))
        buffer_msg.append(request_type)
        buffer_msg.append(field_count)

        # Field-1
        buffer_msg.append(1)
        buffer_msg.extend(struct.pack(">H", len(self.scrips_data)))
        buffer_msg.extend(self.scrips_data)

        # Field-2
        buffer_msg.append(2)
        buffer_msg.extend(struct.pack(">H", 1))
        buffer_msg.append(self.channel_num)
        return buffer_msg

    def __access_token_msg(self) -> bytearray:
        """
        Create a message in bytearray for token.

        Returns:
            bytearray: The token message in bytearray format.
        """
        buffer_size = 18 + len(self.__hsm_token) + len(self.source)

        # Create the byte buffer
        byte_buffer = bytearray()

        # Pack data length into the byte buffer
        byte_buffer.extend(struct.pack("!H", buffer_size - 2))

        # Set ReqType
        byte_buffer.extend(bytes([1]))

        # Set FieldCount
        byte_buffer.extend(bytes([4]))

        # Field-1: AuthToken
        field1_id = 1
        field1_size = len(self.__hsm_token)
        byte_buffer.extend(bytes([field1_id]))
        byte_buffer.extend(struct.pack("!H", field1_size))
        byte_buffer.extend(self.__hsm_token.encode())

        # Field-2
        field2_id = 2
        field2_size = 1
        byte_buffer.extend(bytes([field2_id]))
        byte_buffer.extend(struct.pack("!H", field2_size))
        byte_buffer.extend(self.mode.encode("utf-8"))

        # Field-3
        field3_id = 3
        field3_size = 1
        byte_buffer.extend(bytes([field3_id]))
        byte_buffer.extend(struct.pack("!H", field3_size))
        byte_buffer.extend(bytes([1]))

        # Field-4: self.source
        field4_id = 4
        field4_size = len(self.source)
        byte_buffer.extend(bytes([field4_id]))
        byte_buffer.extend(struct.pack("!H", field4_size))
        byte_buffer.extend(self.source.encode())

        return byte_buffer

    def __lite_mode_msg(self) -> bytearray:
        """
        Create a message in bytearray for lite mode connection.

        Returns:
            bytearray: The lite mode message in bytearray format.
        """
        data = bytearray()

        data.extend(struct.pack(">H", 0))

        data.extend(struct.pack("B", 12))

        data.extend(struct.pack("B", 2))

        channel_bits = 0

        if self.channel_num < 64 and self.channel_num > 0:
            channel_bits |= 1 << self.channel_num

        # Field-1
        field_1 = bytearray()
        field_1.extend(struct.pack("B", 1))
        field_1.extend(struct.pack(">H", 8))
        field_1.extend(struct.pack(">Q", channel_bits))
        data.extend(field_1)

        # Field-2
        field_2 = bytearray()
        field_2.extend(struct.pack("B", 2))
        field_2.extend(struct.pack(">H", 1))
        field_2.extend(struct.pack("B", 76))
        data.extend(field_2)

        return data

    def __full_mode_msg(self) -> bytearray:
        """
        Create a message in bytearray for full mode connection.

        Returns:
            bytearray: The full mode message in bytearray format.
        """
        data = bytearray()

        data.extend(struct.pack(">H", 0))

        data.extend(struct.pack("B", 12))

        data.extend(struct.pack("B", 2))

        channel_bits = 0

        if self.channel_num < 64 and self.channel_num > 0:
            channel_bits |= 1 << self.channel_num

        # Field-1
        field_1 = bytearray()
        field_1.extend(struct.pack("B", 1))
        field_1.extend(struct.pack(">H", 8))
        field_1.extend(struct.pack(">Q", channel_bits))

        data.extend(field_1)

        # Field-2
        field_2 = bytearray()
        field_2.extend(struct.pack("B", 2))
        field_2.extend(struct.pack(">H", 1))
        field_2.extend(struct.pack("B", 70))

        data.extend(field_2)

        return data
