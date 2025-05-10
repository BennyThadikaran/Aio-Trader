import hashlib
import pickle
from datetime import datetime
from pathlib import Path
from typing import Collection, Optional, Union

from throttler import Throttler

from ..AbstractBroker import AbstractBroker
from ..utils import configure_default_logger

default_throttlers = [Throttler(rate_limit=10)]

quote_throttlers = [Throttler(rate_limit=1)]

order_throttlers = [
    Throttler(rate_limit=10),
    Throttler(rate_limit=200, period=60),
]

data_throttlers = [Throttler(rate_limit=3)]


class Kite(AbstractBroker):
    """
    Unofficial implementation of Zerodha Kite API using aiohttp for async requests

    Implements :py:obj:`AbstractBroker`

    :param enctoken: Optional Web or browser token from a previous login
    :type enctoken: Optional[str]
    :param access_token: Api login token from a previous login
    :type access_token: Optional[str]

    All arguments are Optional

    :py:obj:`enctoken` or :py:obj:`access_token` if available can be reused to login.

    .. code:: bash

        # Successful request
        HTTP/1.1 200 OK
        Content-Type: application/json

        {
            "status": "success",
            "data": {}
        }

        # Failed request
        HTTP/1.1 500 Server error
        Content-Type: application/json

        {
            "status": "error",
            "message": "Error message",
            "error_type": "GeneralException"
        }
    """

    # Exchanges
    EXCHANGE_NSE = "NSE"
    EXCHANGE_BSE = "BSE"
    EXCHANGE_NFO = "NFO"
    EXCHANGE_CDS = "CDS"
    EXCHANGE_BFO = "BFO"
    EXCHANGE_MCX = "MCX"
    EXCHANGE_BCD = "BCD"

    # Products
    PRODUCT_MIS = "MIS"
    PRODUCT_CNC = "CNC"
    PRODUCT_NRML = "NRML"
    PRODUCT_CO = "CO"

    # Order types
    ORDER_TYPE_MARKET = "MARKET"
    ORDER_TYPE_LIMIT = "LIMIT"
    ORDER_TYPE_SLM = "SL-M"
    ORDER_TYPE_SL = "SL"

    # Varities
    VARIETY_REGULAR = "regular"
    VARIETY_CO = "co"
    VARIETY_AMO = "amo"
    VARIETY_ICEBERG = "iceberg"
    VARIETY_AUCTION = "auction"

    # Transaction type
    TRANSACTION_TYPE_BUY = "BUY"
    TRANSACTION_TYPE_SELL = "SELL"

    # Validity
    VALIDITY_DAY = "DAY"
    VALIDITY_IOC = "IOC"
    VALIDITY_TTL = "TTL"

    # Position Type
    POSITION_TYPE_DAY = "day"
    POSITION_TYPE_OVERNIGHT = "overnight"

    # Margins segments
    MARGIN_EQUITY = "equity"
    MARGIN_COMMODITY = "commodity"

    # GTT order type
    GTT_TYPE_OCO = "two-leg"
    GTT_TYPE_SINGLE = "single"

    # Status constants
    STATUS_COMPLETE = "COMPLETE"
    STATUS_REJECTED = "REJECTED"
    STATUS_CANCELLED = "CANCELLED"

    # GTT order status
    GTT_STATUS_ACTIVE = "active"
    GTT_STATUS_TRIGGERED = "triggered"
    GTT_STATUS_DISABLED = "disabled"
    GTT_STATUS_EXPIRED = "expired"
    GTT_STATUS_CANCELLED = "cancelled"
    GTT_STATUS_REJECTED = "rejected"
    GTT_STATUS_DELETED = "deleted"

    _type = "KITE_CONNECT"

    base_dir = Path(__file__).parent
    base_url = "https://api.kite.trade"
    cookies = None

    def __init__(
        self,
        enctoken: Optional[str] = None,
        access_token: Optional[str] = None,
    ):

        self.cookie_path = self.base_dir / "kite_cookies"
        self.enctoken = enctoken
        self.access_token = access_token

        self.log = configure_default_logger(__name__)

        self._initialise_session(
            headers={"X-Kite-version": "3"},
            throttlers=default_throttlers,
        )

    def _get_cookie(self):
        """Load the pickle format cookie file"""

        return pickle.loads(self.cookie_path.read_bytes())

    def _set_cookie(self, cookies):
        """Save the cookies to pickle formatted file"""

        cookies["expiry"] = (
            datetime.now()
            .replace(
                hour=23,
                minute=59,
                second=59,
            )
            .timestamp()
        )

        self.cookie_path.write_bytes(pickle.dumps(cookies))

    def _set_enctoken(self, token):
        self.req.session.headers.update({"Authorization": f"enctoken {token}"})
        self._type = "KITE_WEB"

    def _set_access_token(self, api_key, token):
        return self.req.session.headers.update(
            {"Authorization": f"token {api_key}:{token}"}
        )

    async def authorize(self, **kwargs) -> None:
        """
        Authorize the User

        :param user_id: Kite Web user-id
        :type user_id: Optional[str]
        :param password: Kite Web password
        :type password: Optional[str]
        :param twofa: An optional OTP string or Callable that returns OTP
        :type twofa: str | Callable | None
        :param request_token: KiteConnect request_token
        :type request_token: Optional[str]
        :param api_key: KiteConnect api key. Required if access_token is passed
        :type api_key: Optional[str]
        :param secret: KiteConnect secret
        :type secret: Optional[str]
        :raises ValueError: if one of `request_token` or `secret` or `api_key` is provided but others are missing.

        - WEB login - requires :py:obj:`user_id`, :py:obj:`password` and :py:obj:`twofa`
        - KiteConnect login - requires :py:obj:`request_token`, :py:obj:`secret` or :py:obj:`access_token`.
        - :py:obj:`enctoken` from web login is stored in a cookie file and reused.

        If no arguments passed, defaults to web login using interactive prompt

        If :py:obj:`enctoken` or :py:obj:`access_token` was provided, update the headers and return

        If :py:obj:`request_token` and :py:obj:`secret` are provided, proceed to KiteConnect login

        Else proceed with WEB login.

        Check if cookie file exists and not expired. Load the `enctoken`, update the headers
        and return

        If no cookie file exists or has expired, prompt for missing arguments, request the
        `enctoken`, update the headers and return.
        """

        request_token = kwargs.get("request_token", None)
        secret = kwargs.get("secret", None)
        user_id = kwargs.get("user_id", None)
        password = kwargs.get("password", None)
        twofa = kwargs.get("twofa", None)
        api_key = kwargs.get("api_key", None)

        if self.enctoken:
            self.log.info("enctoken set")
            return self._set_enctoken(self.enctoken)

        kite_connect_args = (request_token, secret, api_key)

        if any(kite_connect_args) and None in kite_connect_args:
            raise ValueError(
                "`request_token`, `secret` and `api_key` are required for KiteConnect login"
            )

        if self.access_token:
            self.log.info("access_token set")
            return self._set_access_token(api_key, self.access_token)

        login_url = "https://kite.zerodha.com"

        if request_token and secret:
            # API LOGIN
            checksum = hashlib.sha256(
                f"{api_key}{request_token}{secret}".encode("utf-8")
            ).hexdigest()

            response = await self.req.post(
                f"{login_url}/session/token",
                params={
                    "api_key": api_key,
                    "request_token": request_token,
                    "checksum": checksum,
                },
            )

            self.access_token = response["access_token"]

            self.log.info(f"Api login success: {response['login_time']}")

            return self._set_access_token(api_key, self.access_token)

        # WEB LOGIN
        if self.cookie_path.exists():
            self.cookies = self._get_cookie()

            expiry = datetime.fromtimestamp(
                float(self.cookies.get("expiry").value)
            )

            if datetime.now() > expiry:
                self.cookie_path.unlink()
                self.log.info("Cookie expired")
            else:
                # get enctoken from cookies
                self.enctoken = self.cookies.get("enctoken").value
                self.log.info("Reusing enctoken from cookie file")
                return self._set_enctoken(self.enctoken)

        self.log.info("Login required")

        try:
            if user_id is None:
                user_id = input("Enter User id\n> ")

            if password is None:
                password = input("Enter Password\n> ")
        except KeyboardInterrupt:
            await self.close()
            exit("\nUser exit")

        response = await self.req.post(
            f"{login_url}/api/login",
            data=dict(user_id=user_id, password=password),
        )

        request_id = response["data"]["request_id"]
        twofa_type = response["data"]["twofa_type"]

        if callable(twofa):
            otp = twofa()
        elif isinstance(twofa, str):
            otp = twofa
        else:
            try:
                otp = input(f"Please enter {twofa_type} code\n> ")
            except KeyboardInterrupt:
                await self.close()
                exit("\nUser exit")

        response = await self.req.post(
            f"{login_url}/api/twofa",
            data=dict(
                user_id=user_id,
                request_id=request_id,
                twofa_value=otp,
                twofa_type=twofa_type,
                skip_session="",
            ),
        )

        self._set_cookie(self.req.cookies)

        self.enctoken = self.req.cookies.get("enctoken").value

        self._set_enctoken(self.enctoken)
        login_time = datetime.now().isoformat().replace("T", " ")[:19]

        self.log.info(f"Web Login success: {login_time}")

    async def instruments(self, exchange: Optional[str] = None) -> bytes:
        """
        Return a CSV dump of all tradable instruments in binary format

        Example:

        .. code:: python

            with Kite() as kite:
                data = await kite.instruments(kite.EXCHANGE_NSE)

            with open('instruments.csv', 'wb') as f:
                f.write(data)

        .. code:: python

            import pandas as pd
            import io

            # Load data into pandas Dataframe
            df = pd.read_csv(io.BytesIO(data), index_col='tradingsymbol')
        """

        endpoint = "instruments"

        if self._type == "KITE_WEB" and exchange:
            raise ValueError("Exchange parameter cannot be used with Kite Web")

        if exchange:
            endpoint = f"{endpoint}/{exchange}"

        return await self.req.get(f"{self.base_url}/{endpoint}")

    async def quote(self, instruments: Union[str, Collection[str]]) -> dict:
        """Return the full market quotes - ohlc, OI, bid/ask etc

        instrument identified by `exchange:tradingsymbol` example. NSE:INFY

        :param instruments: A str or collection of instruments
        :raises ValueError: If length of instruments collection exceeds 500

        Example:

        .. code:: python

            await kite.quote('NSE:INFY')
            await kite.quote(['NSE:INFY', 'NSE:RELIANCE', 'NSE:HDFCBANK'])
        """

        if not isinstance(instruments, str) and len(instruments) > 500:
            raise ValueError("Instruments length cannot exceed 500")

        return await self.req.get(
            f"{self.base_url}/quote",
            params={"i": instruments},
            throttlers=quote_throttlers,
        )

    async def ohlc(self, instruments: Union[str, Collection[str]]) -> dict:
        """Returns ohlc and last traded price

        instrument identified by `exchange:tradingsymbol` example. NSE:INFY

        :param instruments: A str or collection of instruments
        :raises ValueError: If length of instruments collection exceeds 1000

        Example:

        .. code:: python

            await kite.ohlc('NSE:INFY')
            await kite.ohlc(['NSE:INFY', 'NSE:RELIANCE', 'NSE:HDFCBANK'])
        """

        if not isinstance(instruments, str) and len(instruments) > 1000:
            raise ValueError("Instruments length cannot exceed 1000")

        return await self.req.get(
            f"{self.base_url}/quote/ohlc",
            params={"i": instruments},
            throttlers=quote_throttlers,
        )

    async def ltp(self, instruments: Union[str, Collection[str]]) -> dict:
        """Returns the last traded price

        instrument identified by `exchange:tradingsymbol` example. NSE:INFY

        :param instruments: A str or collection of instruments
        :raises ValueError: If length of instruments collection exceeds 1000

        Example:

        .. code:: python

            await kite.ltp('NSE:INFY')
            await kite.ltp(['NSE:INFY', 'NSE:RELIANCE', 'NSE:HDFCBANK'])
        """

        if not isinstance(instruments, str) and len(instruments) > 1000:
            raise ValueError("Instruments length cannot exceed 1000")

        return await self.req.get(
            f"{self.base_url}/quote/ltp",
            params={"i": instruments},
            throttlers=quote_throttlers,
        )

    async def holdings(self) -> dict:
        """Return the list of long term equity holdings"""

        return await self.req.get(f"{self.base_url}/portfolio/holdings")

    async def positions(self) -> dict:
        """Retrieve the list of short term positions"""

        return await self.req.get(f"{self.base_url}/portfolio/positions")

    async def auctions(self) -> dict:
        """Retrieve the list of auctions that are currently being held"""

        return await self.req.get(f"{self.base_url}/portfolio/auctions")

    async def margins(self, segment: Optional[str] = None) -> dict:
        """Returns funds, cash, and margin information for the user
        for equity and commodity segments

        :param segment: One of `equity` or `commodity`
        :type segment: Optional[str]
        """

        url = f"{self.base_url}/user/margins"

        if segment:
            url = f"{url}/{segment}"

        return await self.req.get(url)

    async def profile(self) -> dict:
        """Retrieve the user profile"""

        return await self.req.get(f"{self.base_url}/user/profile")

    async def historical_data(
        self,
        instrument_token: str,
        from_dt: Union[datetime, str],
        to_dt: Union[datetime, str],
        interval: str,
        continuous=False,
        oi=False,
    ) -> dict:
        """Return historical candle records for a given instrument.

        :param instrument_token:
        :type instrument_token: str
        :param from_dt: ISO format datetime string or datetime
        :type from_dt: datetime.datetime | str
        :param to_dt: ISO format datetime string or datetime
        :type to_dt: datetime.datetime | str
        :param interval: minute, day, 3minute, 5minute, 10minute, 15minute, 30minute, 60minute
        :type interval: str
        :param continuous: Pass True to get continuous data (F & O)
        :type continuous: bool
        :param oi: Pass True to get OI data (F & O)
        :type oi: bool
        """

        kite_web_url = "https://kite.zerodha.com/oms"

        endpoint = f"instruments/historical/{instrument_token}/{interval}"

        if isinstance(from_dt, datetime):
            from_dt = from_dt.isoformat()

        if isinstance(to_dt, datetime):
            to_dt = to_dt.isoformat()

        params = {
            "from": from_dt,
            "to": to_dt,
            "continuous": int(continuous),
            "oi": int(oi),
        }

        if self._type == "KITE_WEB":
            url = kite_web_url
        else:
            url = self.base_url

        return await self.req.get(
            f"{url}/{endpoint}",
            params=params,
            throttlers=data_throttlers,
        )

    async def place_order(
        self,
        variety: str,
        exchange: str,
        tradingsymbol: str,
        transaction_type: str,
        quantity: int,
        product: str,
        order_type: str,
        price: Optional[float] = None,
        validity: Optional[str] = None,
        validity_ttl: Optional[int] = None,
        disclosed_quantity: Optional[int] = None,
        trigger_price: Optional[float] = None,
        iceberg_legs: Optional[int] = None,
        iceberg_quantity: Optional[int] = None,
        auction_number: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> dict:
        """Place an order of a particular variety

        :param variety: One of `regular`, `co`, `amo`, `iceberg`, `auction`
        :type variety: str
        :param exchange: One of `NSE`, `BSE`, `NFO`, `CDS`, `BFO`, `MCX`, `BCD`
        :type exchange: str,
        :param tradingsymbol: Stock symbol name
        :type tradingsymbol: str
        :param transaction_type: One of `BUY` or `SELL`
        :type transaction_type: str
        :param quantity: Quantity to transact
        :type quantity: int
        :param product: One of `MIS`, `CNC`, `NRML`, `CO`
        :type product: str
        :param order_type: One of `MARKET`, `LIMIT`, `SL-M`, `SL`
        :type order: str
        :param price: The price to execute the order at (for LIMIT orders)
        :type price: Optional[float] = None,
        :param validity: One of `DAY`, `IOC`, `TTL`
        :type validity: Optional[str] = None
        :param validity_ttl: Order life span in minutes for TTL validity orders
        :type validity_ttl: Optional[int] = None,
        :param disclosed_quantity: Disclosed quantity (for equity trades)
        :type disclosed_quantity: Optional[int] = None
        :param trigger_price: Price at which an order should trigger (SL, SL-M)
        :type trigger_price: Optional[float] = None
        :param iceberg_legs: Total number of legs for iceberg order type (Between 2 and 10)
        :type iceberg_legs: Optional[int] = None
        :param iceberg_quantity: Split quantity for each iceberg leg order (qty/iceberg_legs)
        :type iceberg_quantity: Optional[int] = None
        :param auction_number: A unique identifier for a particular auction
        :type auction_number: Optional[str] = None
        :param tag: An optional tag to identify an order (alphanumeric, max 20 chars)
        :type tag: Optional[str] = None

        **Parameters are not validated**
        """

        params = {k: v for k, v in locals().items() if v is not None}

        params.pop("self")

        return await self.req.post(
            f"{self.base_url}/orders/{variety}",
            data=params,
            throttlers=order_throttlers,
        )

    async def modify_order(
        self,
        variety: str,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        order_type: Optional[str] = None,
        trigger_price: Optional[float] = None,
        validity: Optional[str] = None,
        disclosed_quantity: Optional[int] = None,
    ) -> dict:
        """Modify an open order.

        :param variety: One of `regular`, `co`, `amo`, `iceberg`, `auction`
        :type variety: str
        :param order_id:
        :type order_id: str
        :param quantity:
        :type quantity: Optional[int] = None
        :param price:
        :type price: Optional[float] = None
        :param order_type:
        :type order_type: Optional[str] = None
        :param trigger_price:
        :type trigger_price: Optional[float] = None
        :param validity:
        :type validity: Optional[str] = None
        :param disclosed_quantity:
        :type disclosed_quantity: Optional[int] = None
        """

        params = {k: v for k, v in locals().items() if v}

        params.pop("self")

        return await self.req.put(
            f"{self.base_url}/orders/{variety}/{order_id}",
            data=params,
            throttlers=order_throttlers,
        )

    async def cancel_order(self, variety: str, order_id: str) -> dict:
        """Cancel an order.

        :param variety: One of `regular`, `co`, `amo`, `iceberg`, `auction`
        :type variety: str
        :param order_id:
        :type order_id: str
        """

        return await self.req.delete(
            f"{self.base_url}/orders/{variety}/{order_id}",
            throttlers=order_throttlers,
        )

    async def orders(self) -> dict:
        """Get list of all orders for the day"""

        return await self.req.get(
            f"{self.base_url}/orders", throttlers=order_throttlers
        )

    async def order_history(self, order_id: str) -> dict:
        """Get history of individual orders

        :param order_id:
        :type order_id: str
        """

        return await self.req.get(
            f"{self.base_url}/orders/{order_id}", throttlers=order_throttlers
        )

    async def trades(self) -> dict:
        """Get the list of all executed trades for the day"""

        return await self.req.get(
            f"{self.base_url}/trades", throttlers=order_throttlers
        )

    async def order_trades(self, order_id: str) -> dict:
        """Get the the trades generated by an order

        :param order_id:
        :type order_id: str
        """

        return await self.req.get(
            f"{self.base_url}/orders/{order_id}/trades",
            throttlers=order_throttlers,
        )
