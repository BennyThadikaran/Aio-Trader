from pathlib import Path
from typing import Optional, Union, Collection
from throttler import Throttler
from datetime import datetime
import pickle, logging, hashlib
from ..AbstractBroker import AbstractBroker
from ..utils import configure_default_logger

quote_throttler = Throttler(rate_limit=1)
hist_throttler = Throttler(rate_limit=3)
orders_throttler = Throttler(rate_limit=10)


class Kite(AbstractBroker):
    """
    Unofficial implementation of Zerodha Kite api
    using aiohttp for async requests

    All initialization arguments are Optional

    logger if not provided will initialize a default logger.

    In case of previous login, the enctoken or access_token and api_key
    can be passed.

    ValueError is raised if access_token is provided and api_key is missing

    :param enctoken: Optional Web or browser token from a previous login
    :type enctoken: Optional[str]
    :param access_token: Api login token from a previous login
    :type access_token: Optional[str]
    :param logger: Instance of logging.Logger
    :type logger: Optional[logging.Logger]
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

    base_dir = Path(__file__).parent
    base_url = "https://api.kite.trade"
    cookies = None

    def __init__(
        self,
        enctoken: Optional[str] = None,
        access_token: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):

        self.cookie_path = self.base_dir / "kite_cookies"
        self.enctoken = enctoken
        self.access_token = access_token

        self.log = logger if logger else configure_default_logger()

        self._initialise_session(
            headers={"X-Kite-version": "3"},
            throttler=Throttler(rate_limit=10),
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

    def _set_access_token(self, api_key, token):
        return self.req.session.headers.update(
            {"Authorization": f"token {api_key}:{token}"}
        )

    async def authorize(self, **kwargs) -> None:
        """
        Authorize the User

        :param user_id: Kite Web user id
        :type user_id: Optional[str]
        :param password: Kite Web password
        :type password: Optional[str]
        :param twofa: An optional OTP string or Callable that returns OTP
        :type twofa: Union[str, Callable, None]
        :param request_token: KiteConnect request_token
        :type request_token: Optional[str]
        :param api_key: KiteConnect api key. Required if access_token is passed
        :type api_key: Optional[str]
        :param secret: KiteConnect secret
        :type secret: Optional[str]

        WEB login - requires user_id, password and twofa or enctoken

            - enctoken from web login is stored in a cookie file and reused

        KiteConnect/API login - requires request_token, secret or access_token.

            - api_key is required for Api login.
            - ValueError is raised if api_key is missing

        If no arguments passed, defaults to web login using interactive prompt

        if enctoken or access_token is provided, update the headers and return

        if request_token and secret are provided, proceed to API login

        Check if cookie file exists and load the enctoken, update the headers
        and return

        Else proceed with WEB login. Prompt for missing arguments, request the
        enctoken, update the headers and return
        """
        request_token = kwargs.get("request_token", None)
        secret = kwargs.get("secret", None)
        user_id = kwargs.get("user_id", None)
        password = kwargs.get("password", None)
        twofa = kwargs.get("twofa", None)
        api_key = kwargs.get("api_key", None)

        if (request_token and not secret) or (secret and not request_token):
            raise ValueError("Both request_token and secret are required")

        if request_token and secret and not api_key:
            raise ValueError("No api_key provided during initialization")

        if self.enctoken:
            if not api_key:
                raise ValueError(
                    "api_key is required, when access_token is passed"
                )

            self.log.info("enctoken set")
            return self._set_enctoken(self.enctoken)

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
        """return a CSV dump of all tradable instruments"""

        endpoint = "instruments"

        if exchange:
            endpoint = f"{endpoint}/{exchange}"

        return await self.req.get(f"{self.base_url}/{endpoint}")

    async def quote(self, instruments: Union[str, Collection[str]]):
        """Return the full market quotes - ohlc, OI, bid/ask etc"""

        if not isinstance(instruments, str) and len(instruments) > 500:
            raise ValueError("Instruments length cannot exceed 500")

        return await self.req.get(
            f"{self.base_url}/quote",
            params={"i": instruments},
            throttle=quote_throttler,
        )

    async def ohlc(self, instruments: Union[str, Collection[str]]):
        """Returns ohlc and last traded price"""

        if not isinstance(instruments, str) and len(instruments) > 1000:
            raise ValueError("Instruments length cannot exceed 1000")

        return await self.req.get(
            f"{self.base_url}/quote/ohlc",
            params={"i": instruments},
            throttle=quote_throttler,
        )

    async def ltp(self, instruments: Union[str, Collection[str]]):
        """Returns the last traded price"""

        if not isinstance(instruments, str) and len(instruments) > 1000:
            raise ValueError("Instruments length cannot exceed 1000")

        return await self.req.get(
            f"{self.base_url}/quote/ltp",
            params={"i": instruments},
            throttle=quote_throttler,
        )

    async def holdings(self):
        """Return the list of long term equity holdings"""

        return await self.req.get(f"{self.base_url}/portfolio/holdings")

    async def positions(self):
        """Retrieve the list of short term positions"""

        return await self.req.get(f"{self.base_url}/portfolio/positions")

    async def auctions(self):
        """Retrieve the list of auctions that are currently being held"""

        return await self.req.get(f"{self.base_url}/portfolio/auctions")

    async def margins(self, segment: Optional[str] = None):
        """Returns funds, cash, and margin information for the user
        for equity and commodity segments"""

        url = f"{self.base_url}/user/margins"

        if segment:
            url = f"{url}/{segment}"

        return await self.req.get(url)

    async def profile(self):
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
    ):
        """return historical candle records for a given instrument."""

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

        return await self.req.get(
            f"{self.base_url}/{endpoint}",
            params=params,
            throttle=hist_throttler,
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
    ):
        """Place an order of a particular variety"""

        params = {k: v for k, v in locals().items() if v is not None}

        params.pop("self")

        return await self.req.post(
            f"{self.base_url}/orders/{variety}",
            data=params,
            throttle=orders_throttler,
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
    ):
        """Modify an open order."""

        params = {k: v for k, v in locals().items() if v}

        params.pop("self")

        return await self.req.put(
            f"{self.base_url}/orders/{variety}/{order_id}",
            data=params,
            throttle=orders_throttler,
        )

    async def cancel_order(self, variety: str, order_id: str):
        """Cancel an order."""

        return await self.req.delete(
            f"{self.base_url}/orders/{variety}/{order_id}",
            throttle=orders_throttler,
        )

    async def orders(self):
        """Get list of all orders for the day"""

        return await self.req.get(
            f"{self.base_url}/orders", throttle=orders_throttler
        )

    async def order_history(self, order_id: str):
        """Get history of individual orders"""

        return await self.req.get(
            f"{self.base_url}/orders/{order_id}", throttle=orders_throttler
        )

    async def trades(self):
        """Get the list of all executed trades for the day"""

        return await self.req.get(
            f"{self.base_url}/trades", throttle=orders_throttler
        )

    async def order_trades(self, order_id: str):
        """Get the the trades generated by an order"""

        return await self.req.get(
            f"{self.base_url}/orders/{order_id}/trades",
            throttle=orders_throttler,
        )
