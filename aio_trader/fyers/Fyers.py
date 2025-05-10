import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import List, Optional

import aiohttp
from throttler import Throttler

from ..AbstractBroker import AbstractBroker
from ..utils import configure_default_logger


class Config:

    # URL's
    API = "https://api-t1.fyers.in/api/v3"
    DATA_API = "https://api-t1.fyers.in/data"

    # Endpoint
    get_profile = "/profile"
    tradebook = "/tradebook"
    positions = "/positions"
    holdings = "/holdings"
    convert_position = "/positions"
    funds = "/funds"
    orders_endpoint = "/orders/sync"
    gtt_orders_sync = "/gtt/orders/sync"
    orderbook = "/orders"
    gtt_orders = "/gtt/orders"
    market_status = "/marketStatus"
    auth = "/generate-authcode"
    generate_access_token = "/validate-authcode"
    generate_data_token = "/data-token"
    data_vendor_td = "/truedata-ws"
    multi_orders = "/multi-order/sync"
    history = "/history"
    quotes = "/quotes"
    market_depth = "/depth"
    option_chain = "/options-chain-v3"
    multileg_orders = "/multileg/orders/sync"
    logout = "/logout"
    refresh_token = "/validate-refresh-token"


class FyersAuth:
    """
    Fyers class for generating access token

    :param client_id: APP_ID of the created app.
    :type client_id: str
    :param redirect_uri: URL provided when creating fyers app.
    :type redirect_uri: str
    :param secret_key: App secret key of the created app.
    :type secret_key: str
    :param state: A random string used to verify the request
    :type state: str
    :param scope: Default None.
    :type scope: Optional[str]
    :param nonce: Default None. A random string used to verify the auth token
    :type nonce: Optional[str]

    .. code:: python

        import webbrowser

        from aio_trader.fyers import FyersAuth

        fyers_auth = FyersAuth(
            client_id="CLIENT_ID",
            redirect_uri="https://someurl.com",
            state="RANDOM_STRING",
            secret_key="SECRET_KEY",
            nonce="OTHER_RANDOM_STRING"
        )

        auth_url = auth.generate_authcode()

        # After redirect auth_code is available in the redirect url params
        webbrowser.open(auth_url, new=1)

        auth_code = "Paste the auth_code generated from the first request"

        response = fyers_auth.generate_token(auth_code)

        if "access_token":
            access_token = response["access_token"]
        else:
            print("Failed requesting access_token")

    """

    def __init__(
        self,
        client_id: str,
        redirect_uri: str,
        secret_key: str,
        state: Optional[str] = None,
        scope: Optional[str] = None,
        nonce: Optional[str] = None,
    ):
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.scope = scope
        self.state = state
        self.nonce = nonce
        self.secret_key = secret_key
        self.session = aiohttp.ClientSession()

    async def close(self):
        if not self.session.closed:
            await self.session.close()

    def generate_authcode(self) -> str:
        """
        Returns a url to generate the auth token
        """
        data = dict(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
            response_type="code",
            state=self.state,
        )

        if self.scope:
            data["scope"] = self.scope

        if self.nonce:
            data["nonce"] = self.nonce

        url_params = urllib.parse.urlencode(data)
        return f"{Config.API}{Config.auth}?{url_params}"

    async def generate_token(self, auth_code: str) -> dict:
        """
        Makes a request for an access token

        :param auth_code: `auth_code` received after logging into fyers using generate_authcode().
        :type auth_code: str
        """
        data = dict(
            grant_type="authorization_code",
            appIdHash=self.__get_hash().hexdigest(),
            code=auth_code,
        )

        async with self.session.post(
            f"{Config.API}{Config.generate_access_token}",
            json=data,
        ) as response:
            return await response.json()

    async def refresh_token(self, refresh_token: str, pin: str) -> dict:
        """
        Refresh the access token using the refresh_token and user pin.

        Refresh token is valid for 15 days.

        :param refresh_token: refresh_token received from generate_token()
        :type refresh_token: str
        :param pin: User login pin
        :type pin: str
        """
        data = dict(
            grant_type="refresh_token",
            appIdHash=self.__get_hash().hexdigest(),
            refresh_token=refresh_token,
            pin=pin,
        )

        async with self.session.post(
            f"{Config.API}{Config.refresh_token}",
            json=data,
        ) as response:
            return await response.json()

    def __get_hash(self):
        return hashlib.sha256(f"{self.client_id}:{self.secret_key}".encode())


class Fyers(AbstractBroker):
    """
    Unofficial implementation of Fyers API using aiohttp for async requests

    :param client_id: APP_ID of the created app.
    :type client_id: str
    :param token: Api login token from a previous login
    :type token: Optional[str]

    All arguments are Optional

    :py:obj:`enctoken` or :py:obj:`access_token` if available can be reused to login.
    """

    def __init__(
        self,
        client_id: str,
        token: str,
    ):
        base_dir = Path(__file__).parent
        self.cookie_path = base_dir / "fyers_cookies"
        self.client_id = client_id

        self.log = configure_default_logger(__name__)

        self._initialise_session(
            headers={
                "Authorization": f"{self.client_id}:{token}",
                "Content-Type": "application/json",
                "version": "3",
            },
            throttlers=[
                Throttler(rate_limit=10, period=1),
                Throttler(rate_limit=200, period=60),
                Throttler(rate_limit=100000, period=24 * 60 * 60),
            ],
        )

    async def authorize(self, **kwargs) -> None:
        """Not required can be skipped"""
        pass

    async def get_profile(self) -> dict:
        """
        Retrieves the user profile information.
        """
        return await self.req.get(f"{Config.API}{Config.get_profile}")

    async def tradebook(self) -> dict:
        """
        Retrieves daily trade details of the day.
        """
        return await self.req.get(f"{Config.API}{Config.tradebook}")

    async def funds(self) -> dict:
        """
        Retrieves funds details.
        """
        return await self.req.get(f"{Config.API}{Config.funds}")

    async def positions(self) -> dict:
        """
        Retrieves information about current open positions.
        """
        return await self.req.get(f"{Config.API}{Config.positions}")

    async def holdings(self) -> dict:
        """
        Retrieves information about current holdings.
        """
        return await self.req.get(f"{Config.API}{Config.holdings}")

    async def logout(self) -> dict:
        """
        Invalidates the access token.
        """
        return await self.req.post(f"{Config.API}{Config.logout}")

    async def get_orders(self, data: dict) -> dict:
        """
        Retrieves order details by ID.

        :param data: The data containing the order ID.
        :type data: dict
        """
        response = await self.req.get(f"{Config.API}{Config.orderbook}")

        id_list = data["id"].split(",")

        response["orderBook"] = [
            order for order in response["orderBook"] if order["id"] in id_list
        ]

        return response

    async def orderbook(self, data: Optional[dict] = None) -> dict:
        """
        Retrieves the order information.

        :param data: Default None. The data containing the order ID.
        :type data: Optional[dict]
        """
        return await self.req.get(
            f"{Config.API}{Config.orderbook}", params=data
        )

    async def gtt_orderbook(self, data: Optional[dict] = None) -> dict:
        """
        Retrieves the gtt order information.

        :param data: Default None.
        :type data: Optional[dict]
        """
        return await self.req.get(
            f"{Config.API}{Config.gtt_orders}", params=data
        )

    async def market_status(self) -> dict:
        """
        Retrieves market status.
        """
        return await self.req.get(f"{Config.DATA_API}{Config.market_status}")

    async def convert_position(self, data: dict) -> dict:
        """
        Converts positions from one product type to another based on the provided details.

        :param data: Dict containing details about the position.
        :type data: dict

        **Data must contain the following keys: values:**

        - symbol (str): Symbol of the positions. Eg: "MCX:SILVERMIC20NOVFUT".
        - positionSide (int): Side of the positions. 1 for open long positions, -1 for open short positions.
        - convertQty (int): Quantity to be converted. Should be in multiples of lot size for derivatives.
        - convertFrom (str): Existing product type of the positions. (CNC positions cannot be converted)
        - convertTo (str): The new product type to convert the positions to.

        """
        return await self.req.get(
            f"{Config.API}{Config.convert_position}", params=data
        )

    async def cancel_order(self, data: dict) -> dict:
        """
        Cancel order.

        :param data: The data containing the order ID.
        :type data: dict

        **Data must contain the following keys: values:**

        - id (str, optional): ID of the position to close.
          If not provided, all open positions will be closed.

        """
        return await self.req.delete(
            f"{Config.API}{Config.orders_endpoint}", json=data
        )

    async def cancel_gtt_order(self, data: dict) -> dict:
        """
        Cancel order.

        :param data: The data containing the order ID.
        :type data: dict

        **Data must contain the following keys: values:**

        - id (str): Unique identifier for the order to be cancelled,
          e.g., "25010700000001".

        """
        return await self.req.delete(
            f"{Config.API}{Config.gtt_orders_sync}", json=data
        )

    async def place_order(self, data: dict) -> dict:
        """
        Places an order based on the provided data.

        :param data: A dictionary containing the order details
        :type data: dict

        **Data dict must contain the following keys: values:**

        - 'productType' (str): Type of the product.
          Possible values: 'CNC', 'INTRADAY', 'MARGIN', 'CO', 'BO'.
        - 'side' (int): Side of the order. 1 for Buy, -1 for Sell.
        - 'symbol' (str): Symbol of the product. Eg: 'NSE:SBIN-EQ'.
        - 'qty' (int): Quantity of the product. Should be in multiples of
          lot size for derivatives.
        - 'disclosedQty' (int): Default: 0. Disclosed quantity.
          Allowed only for equity.
        - 'type' (int): Type of the order. 1 for Limit Order,
          2 for Market Order, 3 for Stop Order (SL-M),
          4 for Stoplimit Order (SL-L).
        - 'validity' (str): Validity of the order. Possible values:
          'IOC' (Immediate or Cancel), 'DAY' (Valid till the end of the day).
        - 'filledQty' (int): Filled quantity. Default: 0.
        - 'limitPrice' (float): Default: 0. Valid price for Limit and Stoplimit
          orders.
        - 'stopPrice' (float): Default: 0. Valid price for Stop and Stoplimit
          orders.
        - 'offlineOrder' (bool): Specifies if the order is placed when the
          market is open (False) or as an AMO order (True).

        """
        return await self.req.post(
            f"{Config.API}{Config.orders_endpoint}", json=data
        )

    async def place_gtt_order(self, data: dict) -> dict:
        """
        Places an order based on the provided data.

        :param data: A dictionary containing the order details.
        :type data: dict

        data (dict):

        - 'id*' (str): Unique identifier for the order to be modified,
          e.g., "25010700000001".
        - 'side' (int): Indicates the side of the order: 1 for buy,
          -1 for sell.
        - 'symbol' (str): The instrument's unique identifier,
          e.g., "NSE:CHOLAFIN-EQ"
        - 'productType*' (str): The product type for the order.
          Valid values: "CNC", "MARGIN", "MTF".
        - 'orderInfo*' (object): Contains information about the
          GTT/OCO order legs.
        - 'orderInfo.leg1*' (object): Details for GTT order leg.
          Mandatory for all orders.
        - 'orderInfo.leg1.price*' (number): Price at which the order.
        - 'orderInfo.leg1.triggerPrice' (number): Trigger price for the GTT
          order. NOTE: for OCO order this leg trigger price should be always
          above LTP
        - 'orderInfo.leg1.qty*' (int): Quantity for the GTT order leg.
        - 'orderInfo.leg2*' (object): Details for OCO order leg. Optional and
          included only for OCO orders.
        - 'orderInfo.leg2.price*' (number): Price at which the second leg of
          the OCO order should be placed.
        - 'orderInfo.leg2.triggerPrice*' (number): Trigger price for the second
          leg of the OCO order.NOTE: for OCO order this leg trigger price should be always below LTP
        - 'orderInfo.leg2.qty*' (integer): Quantity for the second leg of the
          OCO order.

        """
        return await self.req.post(
            f"{Config.API}{Config.gtt_orders_sync}", json=data
        )

    async def modify_order(self, data: dict) -> dict:
        """
        Modifies the parameters of a pending order based on the provided details.

        :param data: A dictionary containing the order details.
        :type data: dict

        **data (dict):**

        - id (str): ID of the pending order to be modified.
        - limitPrice (float, optional): New limit price for the order.
          Mandatory for Limit/Stoplimit orders.
        - stopPrice (float, optional): New stop price for the order.
          Mandatory for Stop/Stoplimit orders.
        - qty (int, optional): New quantity for the order.
        - type (int, optional): New order type for the order.

        """
        return await self.req.patch(
            f"{Config.API}{Config.orders_endpoint}",
            data=json.dumps(data).encode("utf-8"),
        )

    async def modify_gtt_order(self, data: dict) -> dict:
        """
        Modifies the parameters of a pending order based on the provided details.

        :param data: A dictionary containing the order details.
        :type data: dict

        **data (dict):**

        - id (str): Unique identifier for the order to be modified,
          e.g., "25010700000001"
        - orderInfo* (object): Contains updated information about the GTT/OCO
          order legs.
        - orderInfo.leg1* (object): Details for GTT order leg.
          Mandatory for all modifications.

            - orderInfo.leg1.price* (number): Updated price at which the order
              should be placed.
            - orderInfo.leg1.triggerPrice* (number): Updated trigger price for the
              GTT order.

              **NOTE: for OCO order this leg trigger price should be always above LTP.**
            - orderInfo.leg1.qty** (integer): Updated quantity for the GTT order leg.

        - orderInfo.leg2* (object): Details for OCO order leg. Required if the
          order is an OCO type.

            - orderInfo.leg2.triggerPrice* (number): Updated trigger price for the
              second leg of the OCO order.

              **NOTE: for OCO order this leg trigger price should be always below LTP.**
            - orderInfo.leg2.qty* (integer): Updated quantity for the second leg
              of the OCO order.

        """
        return await self.req.patch(
            f"{Config.API}{Config.gtt_orders_sync}",
            data=json.dumps(data).encode("utf-8"),
        )

    async def exit_positions(self, data: Optional[dict] = None) -> dict:
        """
        Closes open positions based on the provided ID or closes all open positions if ID is not passed.

        :param data: A dictionary containing the position id.
        :type data: dict

        **data (dict):**

        - id (str, optional): ID of the position to close. If not provided, all open positions will be closed.
        """
        return await self.req.delete(
            f"{Config.API}{Config.positions}", json=data or dict(exit_all=1)
        )

    async def place_multileg_order(self, data: dict) -> dict:
        """
        Places an multileg order based on the provided data.

        :param data: A dictionary containing the order details.
        :type data: dict

        **data (dict):**

        - 'productType' (str): Type of the product. Possible values: 'INTRADAY', 'MARGIN'.
        - 'offlineOrder' (bool): Specifies if the order is placed when the market is open (False) or as an AMO order (True).
        - 'orderType' (str): Type of multileg. Possible values: '3L' for 3 legs and '2L' for 2 legs .
        - 'validity' (str): Validity of the order. Possible values: 'IOC' (Immediate or Cancel).
        - legs (dict): A dictionary containing multiple legs order details.

            - 'symbol' (str): Symbol of the product. Eg: 'NSE:SBIN-EQ'.
            - 'qty' (int): Quantity of the product. Should be in multiples of lot size for derivatives.
            - 'side' (int): Side of the order. 1 for Buy, -1 for Sell.
            - 'type' (int): Type of the order. Possible values: 1 for Limit Order.
            - 'limitPrice' (float): Valid price for Limit and Stoplimit orders.

        """
        return await self.req.post(
            f"{Config.API}{Config.multileg_orders}", json=data
        )

    async def cancel_basket_orders(self, data: dict) -> dict:
        """
        Cancels the orders with the provided IDs.

        :param data: A dictionary containing the order details.
        :type data: dict

        **data (dict):**

        - order_ids (list): A list of order IDs to be cancelled.

        """
        return await self.req.delete(
            f"{Config.API}{Config.multi_orders}", json=data
        )

    async def place_basket_orders(self, orders: List[dict]) -> dict:
        """
        Places multiple orders based on the provided details.

        :param orders: A list of dictionaries containing the order details.
        :type orders: List[dict]

        **orders (list):**

        Each dictionary should have the following keys:

        - 'symbol' (str): Symbol of the product. Eg: 'MCX:SILVERM20NOVFUT'.
        - 'qty' (int): Quantity of the product.
        - 'type' (int): Type of the order. 1 for Limit Order, 2 for Market Order, and so on.
        - 'side' (int): Side of the order. 1 for Buy, -1 for Sell.
        - 'productType' (str): Type of the product. Eg: 'INTRADAY', 'CNC', etc.
        - 'limitPrice' (float): Valid price for Limit and Stoplimit orders.
        - 'stopPrice' (float): Valid price for Stop and Stoplimit orders.
        - 'disclosedQty' (int): Disclosed quantity. Allowed only for equity.
        - 'validity' (str): Validity of the order. Eg: 'DAY', 'IOC', etc.
        - 'offlineOrder' (bool): Specifies if the order is placed when the market is open (False) or as an AMO order (True).
        - 'stopLoss' (float): Valid price for CO and BO orders.
        - 'takeProfit' (float): Valid price for BO orders.

        """
        return await self.req.post(
            f"{Config.API}{Config.multi_orders}", json=orders
        )

    async def modify_basket_orders(self, orders: List[dict]):
        """
        Modifies multiple pending orders based on the provided details.

        :param orders: A list of dictionaries containing the order details.
        :type orders: List[dict]

        **orders (list):**

        A list of dictionaries containing the order details to be modified.

        Each dictionary should have the following keys:

        - 'id' (str): ID of the pending order to be modified.
        - 'limitPrice' (float): New limit price for the order. Mandatory for Limit/Stoplimit orders.
        - 'stopPrice' (float): New stop price for the order. Mandatory for Stop/Stoplimit orders.
        - 'qty' (int): New quantity for the order.
        - 'type' (int): New order type for the order.

        Returns:
            The response JSON as a dictionary.
        """
        return await self.req.patch(
            f"{Config.API}{Config.multi_orders}",
            data=json.dumps(orders).encode("utf-8"),
        )

    async def history(self, data: dict) -> dict:
        """
        Fetches candle data based on the provided parameters.

        :param data: Dict containing details of symbol
        :type data: dict

        **Data dict must contain the below keys:**

        - symbol (str): Symbol of the product. Eg: ``NSE:SBIN-EQ``.

        - resolution (str): The candle resolution. Possible values are:
          ``Day`` or ``1D``, ``1``, ``2``, ``3``, ``5``, ``10``, ``15``,
          ``20``, ``30``, ``60``, ``120``, ``240``.

        - date_format (int): Date format flag. 0 to enter the epoch value,
          1 to enter the date format as ``yyyy-mm-dd``.

        - range_from (str): Start date of the records. Accepts epoch value if
          date_format flag is set to 0, or ``yyyy-mm-dd`` format if
          date_format flag is set to 1.

        - range_to (str): End date of the records. Accepts epoch value if
          ``date_format`` flag is set to 0, or ``yyyy-mm-dd`` format if
          ``date_format`` flag is set to 1.

        - cont_flag (int): Flag indicating continuous data and future options.
          Set to 1 for continuous data.

        """
        return await self.req.get(
            f"{Config.DATA_API}{Config.history}", params=data
        )

    async def quotes(self, data: str) -> dict:
        """
        Fetches quotes data for multiple symbols.

        :param symbols: Comma-separated symbols of the products.
            Maximum symbol limit is 50. Eg: 'NSE:SBIN-EQ,NSE:HDFC-EQ'.
        :type symbols: str
        """
        return await self.req.get(
            f"{Config.DATA_API}{Config.quotes}", params=data
        )

    async def depth(self, data: dict) -> dict:
        """
        Fetches market depth data for a symbol.

        :param data: Dict containing symbol name
        :type data: dict

        **data: dict**

        - symbol (str): Symbol of the product. Eg: 'NSE:SBIN-EQ'.
        - ohlcv_flag (int): Flag to indicate whether to retrieve open, high,
          low, closing, and volume quantity. Set to 1 for yes.

        """
        return await self.req.get(
            f"{Config.DATA_API}{Config.market_depth}", params=data
        )

    async def optionchain(self, data: dict) -> dict:
        """
        Fetches option chain data for a given symbol.

        :param data: Dict containing symbol name and strikecount
        :type data: dict

        **data: dict**

        - symbol (str): The symbol of the product. For example,
          'NSE:NIFTY50-INDEX'.
        - timestamp (int): Expiry timestamp of the stock. Use empty for
          current expiry. Example: 1813831200.
        - strikecount (int): Number of strike price data points desired.
          For instance, setting it to 7 provides: 1 INDEX + 7 ITM + 1 ATM +
          7 OTM = 1 INDEX and 15 STRIKE (15 CE + 15 PE).
        """
        return await self.req.get(
            f"{Config.DATA_API}{Config.option_chain}", params=data
        )
