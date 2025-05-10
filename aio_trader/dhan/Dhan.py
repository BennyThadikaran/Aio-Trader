import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from webbrowser import open as web_open

from throttler import Throttler

from ..AbstractBroker import AbstractBroker
from ..utils import configure_default_logger

default_throttlers = [Throttler(rate_limit=20)]

order_throttlers = [
    Throttler(rate_limit=25),
    Throttler(rate_limit=250, period=60),
    Throttler(rate_limit=1000, period=60 * 60),
    Throttler(rate_limit=7000, period=24 * 60 * 60),
]

data_throttlers = [
    Throttler(rate_limit=5),
    Throttler(rate_limit=24 * 60 * 60, period=24 * 60 * 60),
]

quote_throttlers = [Throttler(rate_limit=1)]


class Dhan(AbstractBroker):
    """Unofficial Dhan Class to interact with REST APIs

    :param client_id: Dhan client id
    :type client_id: str
    :param access_token: Dhan access token
    :type access_token: str
    """

    # Constants for Exchange Segment
    NSE = "NSE_EQ"
    BSE = "BSE_EQ"
    CUR = "NSE_CURRENCY"
    MCX = "MCX_COMM"
    FNO = "NSE_FNO"
    NSE_FNO = "NSE_FNO"
    BSE_FNO = "BSE_FNO"
    INDEX = "IDX_I"

    # Constants for Transaction Type
    BUY = "BUY"
    SELL = "SELL"

    # Constants for Product Type
    CNC = "CNC"
    INTRA = "INTRADAY"
    MARGIN = "MARGIN"
    CO = "CO"
    BO = "BO"
    MTF = "MTF"

    # Constants for Order Type
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    SL = "STOP_LOSS"
    SLM = "STOP_LOSS_MARKET"

    # Constants for Validity
    DAY = "DAY"
    IOC = "IOC"

    # CSV URL for Security ID List
    COMPACT_CSV_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
    DETAILED_CSV_URL = (
        "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
    )

    def __init__(
        self,
        client_id: str,
        access_token: str,
    ):
        self.cookie_path = Path("dhan_cookie")
        self.client_id = str(client_id)
        self.access_token = access_token
        self.base_url = "https://api.dhan.co/v2"

        self.log = configure_default_logger(__name__)
        self.headers = {
            "access-token": access_token,
            "Content-type": "application/json",
            "Accept": "application/json",
        }

        self._initialise_session(
            headers=self.headers,
            throttlers=default_throttlers,
        )

        self.headers_w_client_id = self.headers.copy()
        self.headers_w_client_id["client-id"] = client_id

    async def authorize(self, **_):
        """Not required can be skipped"""
        pass

    async def get_order_list(self) -> dict:
        """
        Retrieve a list of all orders requested in a day with their last updated status.
        """

        return await self.req.get(
            f"{self.base_url}/orders",
            throttlers=order_throttlers,
        )

    async def get_order_by_id(self, order_id) -> dict:
        """
        Retrieve the details and status of an order from the orderbook placed during the day.

        :param order_id: The ID of the order to retrieve.
        :type order_id: str
        """
        return await self.req.get(
            f"{self.base_url}/orders/{order_id}",
            throttlers=order_throttlers,
        )

    async def get_order_by_correlationID(self, correlationID) -> dict:
        """
        Retrieve the order status using a field called correlation ID.

        :param corelationID: The correlation ID provided during order placement.
        :type corelationID: str
        """
        return await self.req.get(
            f"{self.base_url}/orders/external/{correlationID}",
            throttlers=order_throttlers,
        )

    async def modify_order(
        self,
        order_id,
        order_type,
        leg_name,
        quantity,
        price,
        trigger_price,
        disclosed_quantity,
        validity,
    ) -> dict:
        """
        Modify a pending order in the orderbook.

        :param order_id: The ID of the order to modify.
        :type order_id: str
        :param order_type: The type of order (e.g., LIMIT, MARKET).
        :type order_type: str
        :param leg_name: The name of the leg to modify.
        :type leg_name: str
        :param quantity: The new quantity for the order.
        :type quantity: str
        :param price: The new price for the order.
        :type price: float
        :param trigger_price: The trigger price for the order.
        :type trigger_price: float
        :param disclosed_quantity: The disclosed quantity for the order.
        :type disclosed_quantity: int
        :param validity: The validity of the order.
        :type validity: str

        """
        return await self.req.put(
            f"{self.base_url}/orders/{order_id}",
            throttlers=order_throttlers,
            data=json.dumps(
                dict(
                    dhanClientId=self.client_id,
                    orderId=str(order_id),
                    orderType=order_type,
                    legName=leg_name,
                    quantity=quantity,
                    price=price,
                    disclosedQuantity=disclosed_quantity,
                    triggerPrice=trigger_price,
                    validity=validity,
                )
            ),
        )

    async def cancel_order(self, order_id: str) -> dict:
        """
        Cancel a pending order in the orderbook using the order ID.

        :param order_id: The ID of the order to cancel.
        :type order_id: str
        """
        return await self.req.delete(
            f"{self.base_url}/orders/{order_id}",
            throttlers=order_throttlers,
        )

    async def place_order(
        self,
        security_id,
        exchange_segment,
        transaction_type,
        quantity,
        order_type,
        product_type,
        price,
        trigger_price=0,
        disclosed_quantity=0,
        after_market_order=False,
        validity="DAY",
        amo_time="OPEN",
        bo_profit_value=None,
        bo_stop_loss_Value=None,
        tag=None,
    ) -> dict:
        """
        Place a new order in the Dhan account.

        :param security_id: The ID of the security to trade.
        :type security_id: str
        :param exchange_segment: The exchange segment (e.g., NSE, BSE).
        :type exchange_segment: str
        :param transaction_type: The type of transaction (BUY/SELL).
        :type transaction_type: str
        :param quantity: The quantity of the order.
        :type quantity: int
        :param order_type: The type of order (LIMIT, MARKET, etc.).
        :type order_type: str
        :param product_type: The product type (CNC, INTRA, etc.).
        :type product_type: str
        :param price: The price of the order.
        :type price: float
        :param trigger_price: The trigger price for the order.
        :type trigger_price: float
        :param disclosed_quantity: The disclosed quantity for the order.
        :type disclosed_quantity: int
        :param after_market_order: Flag for after market order.
        :type after_market_order: bool
        :param validity: The validity of the order (DAY, IOC, etc.).
        :type validity: str
        :param amo_time: The time for AMO orders.
        :type amo_time: str
        :param bo_profit_value: The profit value for BO orders.
        :type bo_profit_value: float
        :param bo_stop_loss_Value: The stop loss value for BO orders.
        :type bo_stop_loss_Value: float
        :param tag: Optional correlation ID for tracking.
        :type tag: str

        :raises ValueError: if ``amo_time`` not one of ``PRE_OPEN``, ``OPEN``, ``OPEN_30``, ``OPEN_60``

        """
        payload = dict(
            dhanClientId=self.client_id,
            transactionType=transaction_type.upper(),
            exchangeSegment=exchange_segment.upper(),
            productType=product_type.upper(),
            orderType=order_type.upper(),
            validity=validity.upper(),
            securityId=security_id,
            quantity=int(quantity),
            disclosedQuantity=int(disclosed_quantity),
            price=float(price),
            afterMarketOrder=after_market_order,
            boProfitValue=bo_profit_value,
            boStopLossValue=bo_stop_loss_Value,
        )

        if tag is not None and tag != "":
            payload["correlationId"] = tag

        if after_market_order:
            if amo_time not in ("PRE_OPEN", "OPEN", "OPEN_30", "OPEN_60"):
                raise ValueError(
                    "amo_time value must be ['PRE_OPEN','OPEN','OPEN_30','OPEN_60']"
                )

            payload["amoTime"] = amo_time

        if trigger_price > 0:
            payload["triggerPrice"] = float(trigger_price)
        elif trigger_price == 0:
            payload["triggerPrice"] = 0.0

        return await self.req.post(
            f"{self.base_url}/orders",
            params=json.dumps(payload),
            throttlers=order_throttlers,
        )

    async def place_slice_order(
        self,
        security_id,
        exchange_segment,
        transaction_type,
        quantity,
        order_type,
        product_type,
        price,
        trigger_price=0,
        disclosed_quantity=0,
        after_market_order=False,
        validity="DAY",
        amo_time="OPEN",
        bo_profit_value=None,
        bo_stop_loss_Value=None,
        tag=None,
    ) -> dict:
        """
        Place a new slice order in the Dhan account.

        :param security_id: The ID of the security to trade.
        :type security_id: str
        :param exchange_segment: The exchange segment (e.g., NSE, BSE).
        :type exchange_segment: str
        :param transaction_type: The type of transaction (BUY/SELL).
        :type transaction_type: str
        :param quantity: The quantity of the order.
        :type quantity: int
        :param order_type: The type of order (LIMIT, MARKET, etc.).
        :type order_type: str
        :param product_type: The product type (CNC, MIS, etc.).
        :type product_type: str
        :param price: The price of the order.
        :type price: float
        :param trigger_price: The trigger price for the order.
        :type trigger_price: float
        :param disclosed_quantity: The disclosed quantity for the order.
        :type disclosed_quantity: int
        :param after_market_order: Flag for after market order.
        :type after_market_order: bool
        :param validity: The validity of the order (DAY, IOC, etc.).
        :type validity: str
        :param amo_time: The time for AMO orders.
        :type amo_time: str
        :param bo_profit_value: The profit value for BO orders.
        :type bo_profit_value: float
        :param bo_stop_loss_Value: The stop loss value for BO orders.
        :type bo_stop_loss_Value: float
        :param tag: Optional correlation ID for tracking.
        :type tag: str

        :raises ValueError: if ``amo_time`` not one of ``OPEN``, ``OPEN_30``, ``OPEN_60``

        """
        payload = dict(
            dhanClientId=self.client_id,
            transactionType=transaction_type.upper(),
            exchangeSegment=exchange_segment.upper(),
            productType=product_type.upper(),
            orderType=order_type.upper(),
            validity=validity.upper(),
            securityId=security_id,
            quantity=int(quantity),
            disclosedQuantity=int(disclosed_quantity),
            price=float(price),
            afterMarketOrder=after_market_order,
            boProfitValue=bo_profit_value,
            boStopLossValue=bo_stop_loss_Value,
        )

        if tag is not None and tag != "":
            payload["correlationId"] = tag

        if after_market_order:
            if amo_time not in ("OPEN", "OPEN_30", "OPEN_60"):
                raise ValueError(
                    "amo_time value must be ['OPEN','OPEN_30','OPEN_60']"
                )

            payload["amoTime"] = amo_time

        if trigger_price > 0:
            payload["triggerPrice"] = float(trigger_price)
        elif trigger_price == 0:
            payload["triggerPrice"] = 0.0

        return await self.req.post(
            f"{self.base_url}/orders/slicing",
            params=json.dumps(payload),
            throttlers=order_throttlers,
        )

    async def get_positions(self) -> dict:
        """
        Retrieve a list of all open positions for the day.
        """
        return await self.req.get(f"{self.base_url}/positions")

    async def get_holdings(self) -> dict:
        """
        Retrieve all holdings bought/sold in previous trading sessions.
        """
        return await self.req.get(f"{self.base_url}/holdings")

    async def convert_position(
        self,
        from_product_type,
        exchange_segment,
        position_type,
        security_id,
        convert_qty,
        to_product_type,
    ) -> dict:
        """
        Convert Position from Intraday to Delivery or vice versa.

        :param from_product_type: The product type to convert from (e.g., CNC).
        :type from_product_type: str
        :param exchange_segment: The exchange segment (e.g., NSE_EQ).
        :type exchange_segment: str
        :param position_type: The type of position (e.g., LONG).
        :type position_type: str
        :param security_id: The ID of the security to convert.
        :type security_id: str
        :param convert_qty: The quantity to convert.
        :type convert_qty: int
        :param to_product_type: The product type to convert to (e.g., CNC).
        :type to_product_type: str

        """
        return await self.req.post(
            f"{self.base_url}/positions/convert",
            data=json.dumps(
                dict(
                    dhanClientId=self.client_id,
                    fromProductType=from_product_type,
                    exchangeSegment=exchange_segment,
                    positionType=position_type,
                    securityId=security_id,
                    convertQty=convert_qty,
                    toProductType=to_product_type,
                )
            ),
        )

    async def place_forever(
        self,
        security_id,
        exchange_segment,
        transaction_type,
        product_type,
        order_type,
        quantity,
        price,
        trigger_Price,
        order_flag="SINGLE",
        disclosed_quantity=0,
        validity="DAY",
        price1=0,
        trigger_Price1=0,
        quantity1=0,
        tag=None,
        symbol="",
    ) -> dict:
        """
        Place a new forever order in the Dhan account.

        :param security_id: The ID of the security to trade.
        :type security_id: str
        :param exchange_segment: The exchange segment (e.g., NSE, BSE).
        :type exchange_segment: str
        :param transaction_type: The type of transaction (BUY/SELL).
        :type transaction_type: str
        :param product_type: The product type (e.g., CNC, INTRA).
        :type product_type: str
        :param order_type: The type of order (LIMIT, MARKET, etc.).
        :type order_type: str
        :param quantity: The quantity of the order.
        :type quantity: int
        :param price: The price of the order.
        :type price: float
        :param trigger_Price: The trigger price for the order.
        :type trigger_Price: float
        :param order_flag: The order flag (default is "SINGLE").
        :type order_flag: str
        :param disclosed_quantity: The disclosed quantity for the order.
        :type disclosed_quantity: int
        :param validity: The validity of the order (DAY, IOC, etc.).
        :type validity: str
        :param price1: The secondary price for the order.
        :type price1: float
        :param trigger_Price1: The secondary trigger price for the order.
        :type trigger_Price1: float
        :param quantity1: The secondary quantity for the order.
        :type quantity1: int
        :param tag: Optional correlation ID for tracking.
        :type tag: str
        :param symbol: The trading symbol for the order.
        :type symbol: str

        """
        payload = dict(
            dhanClientId=self.client_id,
            orderFlag=order_flag,
            transactionType=transaction_type.upper(),
            exchangeSegment=exchange_segment.upper(),
            productType=product_type.upper(),
            orderType=order_type.upper(),
            validity=validity.upper(),
            tradingSymbol=symbol,
            securityId=security_id,
            quantity=int(quantity),
            disclosedQuantity=int(disclosed_quantity),
            price=float(price),
            triggerPrice=float(trigger_Price),
            price1=float(price1),
            triggerPrice1=float(trigger_Price1),
            quantity1=int(quantity1),
        )

        if tag != None and tag != "":
            payload["correlationId"] = tag

        return await self.req.post(
            f"{self.base_url}/forever/orders",
            data=json.dumps(payload),
            throttlers=order_throttlers,
        )

    async def modify_forever(
        self,
        order_id,
        order_flag,
        order_type,
        leg_name,
        quantity,
        price,
        trigger_price,
        disclosed_quantity,
        validity,
    ) -> dict:
        """
        Modify a forever order based on the specified leg name. The variables that can be modified include price, quantity, order type, and validity.

        :param order_id: The ID of the order to modify.
        :type order_id: str
        :param order_flag: The order flag indicating the type of order (e.g., SINGLE, OCO).
        :type order_flag: str
        :param order_type: The type of order (e.g., LIMIT, MARKET).
        :type order_type: str
        :param leg_name: The name of the leg to modify.
        :type leg_name: str
        :param quantity: The new quantity for the order.
        :type quantity: int
        :param price: The new price for the order.
        :type price: float
        :param trigger_price: The trigger price for the order.
        :type trigger_price: float
        :param disclosed_quantity: The disclosed quantity for the order.
        :type disclosed_quantity: int
        :param validity: The validity of the order.
        :type validity: str

        """
        return await self.req.put(
            f"{self.base_url}/forever/orders/{order_id}",
            data=json.dumps(
                dict(
                    dhanClientId=self.client_id,
                    orderId=str(order_id),
                    orderFlag=order_flag,
                    orderType=order_type,
                    legName=leg_name,
                    quantity=quantity,
                    price=price,
                    disclosedQuantity=disclosed_quantity,
                    triggerPrice=trigger_price,
                    validity=validity,
                )
            ),
            throttlers=order_throttlers,
        )

    async def cancel_forever(self, order_id) -> dict:
        """
        Delete Forever orders using the order id of an order.

        :param order_id: Order id
        :type order_id: str

        """
        return await self.req.delete(
            f"{self.base_url}/forever/orders/{order_id}",
            throttlers=order_throttlers,
        )

    async def get_forever(self) -> list:
        """Retrieve a list of all existing Forever Orders."""
        return await self.req.get(
            f"{self.base_url}/forever/orders",
            throttlers=order_throttlers,
        )

    async def generate_tpin(self) -> dict:
        """
        Generate T-Pin on registered mobile number.
        """
        return await self.req.get(f"{self.base_url}/edis/tpin")

    async def open_browser_for_tpin(
        self, isin, qty, exchange, segment="EQ", bulk=False
    ) -> dict:
        """
        Opens the default web browser to enter T-Pin.

        :param isin: The ISIN of the security.
        :type isin: str
        :param qty: The quantity of the security.
        :type qty: int
        :param exchange: The exchange where the security is listed.
        :type exchange: str
        :param segment: The segment of the exchange (default is 'EQ').
        :type segment: str
        :param bulk: Flag for bulk operations (default is False).
        :type bulk: bool

        """
        data = await self.req.post(
            f"{self.base_url}/edis/form",
            data=json.dumps(
                dict(
                    isin=isin,
                    qty=qty,
                    exchange=exchange,
                    segment=segment,
                    bulk=bulk,
                )
            ),
        )

        form_html = data["edisFormHtml"].replace("\\", "")

        with open("temp_form.html", "w") as f:
            f.write(form_html)

        filename = rf"file:\\\{Path.cwd()}\\temp_form.html"
        web_open(filename)
        return data

    async def edis_inquiry(self, isin) -> dict:
        """
        Inquire about the eDIS status of the provided ISIN.

        :param isin: The ISIN to inquire about.
        :type isin: str

        """
        return await self.req.get(f"{self.base_url}/edis/inquire/{isin}")

    async def kill_switch(
        self, action: Literal["activate", "deactivate"]
    ) -> dict:
        """
        Control kill switch for user, which will disable trading for current trading day.

        :param action: 'activate' or 'deactivate' to control the kill switch.
        :type action: Literal['activate', "deactivate"]

        """
        return await self.req.post(
            f"{self.base_url}/killswitch?killSwitchStatus={action.upper()}"
        )

    async def get_fund_limits(self) -> dict:
        """
        Get all information of your trading account like balance, margin utilized, collateral, etc.
        """
        return await self.req.get(f"{self.base_url}/fundlimit")

    async def margin_calculator(
        self,
        security_id,
        exchange_segment,
        transaction_type,
        quantity,
        product_type,
        price,
        trigger_price=0,
    ) -> dict:
        """
        Calculate the margin required for a trade based on the provided parameters.

        :param security_id: The ID of the security for which the margin is to be calculated.
        :type security_id: str
        :param exchange_segment: The exchange segment (e.g., NSE_EQ) where the trade will be executed.
        :type exchange_segment: str
        :param transaction_type: The type of transaction (BUY/SELL).
        :type transaction_type: str
        :param quantity: The quantity of the security to be traded.
        :type quantity: int
        :param product_type: The product type (e.g., CNC, INTRA) of the trade.
        :type product_type: str
        :param price: The price at which the trade will be executed.
        :type price: float
        :param trigger_price: The trigger price for the trade. Defaults to 0.
        :type trigger_price: float

        """
        payload = dict(
            dhanClientId=self.client_id,
            securityId=security_id,
            exchangeSegment=exchange_segment.upper(),
            transactionType=transaction_type.upper(),
            quantity=int(quantity),
            productType=product_type.upper(),
            price=float(price),
        )

        if trigger_price > 0:
            payload["triggerPrice"] = float(trigger_price)
        elif trigger_price == 0:
            payload["triggerPrice"] = 0.0

        return await self.req.post(
            f"{self.base_url}/margincalculator",
            data=json.dumps(payload),
        )

    async def get_trade_book(self, order_id=None) -> dict:
        """
        Retrieve a list of all trades executed in a day.

        :param order_id: The ID of the specific order to retrieve trades for.
        :type order_id: str, optional

        """
        if order_id is None:
            url = f"{self.base_url}/trades"
        else:
            url = f"{self.base_url}/trades/{order_id}"

        return await self.req.get(url)

    async def get_trade_history(
        self, from_date, to_date, page_number=0
    ) -> dict:
        """
        Retrieve the trade history for a specific date range.

        :param from_date: The start date for the trade history.
        :type from_date: str
        :param to_date: The end date for the trade history.
        :type to_date: str
        :param page_number: The page number for pagination.
        :type page_number: int

        """
        return await self.req.get(
            f"{self.base_url}/trades/{from_date}/{to_date}/{page_number}",
        )

    async def ledger_report(self, from_date, to_date) -> dict:
        """
        Retrieve the ledger details for a specific date range.

        :param from_date: The start date for the trade history.
        :type from_date: str
        :param to_date: The end date for the trade history.
        :type to_date: str

        """
        return await self.req.get(
            f"{self.base_url}/ledger?from-date={from_date}&to-date={to_date}",
        )

    async def intraday_minute_data(
        self,
        security_id,
        exchange_segment,
        instrument_type,
        from_date,
        to_date,
        interval=1,
    ) -> dict:
        """
        Retrieve OHLC & Volume of minute candles for desired instrument for last 5 trading day.

        :param security_id: The ID of the security.
        :type security_id: str
        :param exchange_segment: The exchange segment (e.g., NSE, BSE).
        :type exchange_segment: str
        :param instrument_type: The type of instrument (e.g., stock, option).
        :type instrument_type: str

        :raises ValueError: if interval not one of 1, 5, 15, 25, 60

        """
        payload = dict(
            securityId=security_id,
            exchangeSegment=exchange_segment,
            instrument=instrument_type,
            interval=interval,
            fromDate=from_date,
            toDate=to_date,
        )

        if interval not in [1, 5, 15, 25, 60]:
            raise ValueError("interval value must be ['1','5','15','25','60']")

        payload["interval"] = interval

        return await self.req.post(
            f"{self.base_url}/charts/intraday",
            data=json.dumps(payload),
            throttlers=data_throttlers,
        )

    async def historical_daily_data(
        self,
        security_id,
        exchange_segment,
        instrument_type,
        from_date,
        to_date,
        expiry_code=0,
    ) -> dict:
        """
        Retrieve OHLC & Volume of daily candle for desired instrument.

        :param security_id: Security ID of the instrument.
        :type security_id: str
        :param exchange_segment: The exchange segment (e.g., NSE, BSE).
        :type exchange_segment: str
        :param instrument_type: The type of instrument (e.g., stock, option).
        :type instrument_type: str
        :param expiry_code: The expiry code for derivatives.
        :type expiry_code: str
        :param from_date: The start date for the historical data.
        :type from_date: str
        :param to_date: The end date for the historical data.
        :type to_date: str

        :raises ValueError: if expiry_code not one of ``0``, ``1``, ``2`` ,``3``

        """
        payload = dict(
            securityId=security_id,
            exchangeSegment=exchange_segment,
            instrument=instrument_type,
            expiryCode=expiry_code,
            fromDate=from_date,
            toDate=to_date,
        )

        if expiry_code not in [0, 1, 2, 3]:
            raise ValueError("expiry_code value must be ['0','1','2','3']")

        payload["expiryCode"] = expiry_code

        return await self.req.post(
            f"{self.base_url}/charts/historical",
            data=json.dumps(payload),
            throttlers=data_throttlers,
        )

    async def ticker_data(self, securities) -> dict:
        """
        Retrieve the latest market price for specified instruments.

        :param securities: A dictionary where keys are exchange segments and values are lists of security IDs.
        :type securities: dict

        .. code::python

            securities = {
                "NSE_EQ": [11536],
                "NSE_FNO": [49081, 49082]
            }

        """
        return await self.req.post(
            f"{self.base_url}/marketfeed/ltp",
            data=json.dumps(
                {
                    exchange_segment: security_id
                    for exchange_segment, security_id in securities.items()
                }
            ),
            headers=self.headers_w_client_id,
            throttlers=quote_throttlers,
        )

    async def ohlc_data(self, securities) -> dict:
        """
        Retrieve the Open, High, Low and Close price along with LTP for specified instruments.

        :param securities: A dictionary where keys are exchange segments and values are lists of security IDs.
        :type securities: dict

        .. code::python

            securities = {
                "NSE_EQ": [11536],
                "NSE_FNO": [49081, 49082]
            }

        """
        return await self.req.post(
            f"{self.base_url}/marketfeed/ohlc",
            data=json.dumps(
                {
                    exchange_segment: security_id
                    for exchange_segment, security_id in securities.items()
                }
            ),
            headers=self.headers_w_client_id,
            throttlers=quote_throttlers,
        )

    async def quote_data(self, securities) -> dict:
        """
        Retrieve full details including market depth, OHLC data, OI and volume along with LTP for specified instruments.

        :param securities: A dictionary where keys are exchange segments and values are lists of security IDs.
        :type securities: dict

        .. code::python

            securities = {
                "NSE_EQ": [11536],
                "NSE_FNO": [49081, 49082]
            }

        """
        return await self.req.post(
            f"{self.base_url}/marketfeed/quote",
            data=json.dumps(
                {
                    exchange_segment: security_id
                    for exchange_segment, security_id in securities.items()
                }
            ),
            headers=self.headers_w_client_id,
            throttlers=quote_throttlers,
        )

    async def fetch_security_list(
        self, mode: Literal["compact", "detailed"] = "compact"
    ) -> bytes:
        """
        Fetch CSV file from dhan based on the specified mode and save it to the current directory.

        :param mode: The mode to fetch the CSV ('compact' or 'detailed').
        :type mode: Literal["compact", "detailed"]

        """
        return await self.req.get(
            self.COMPACT_CSV_URL if mode == "compact" else self.DETAILED_CSV_URL
        )

    async def option_chain(
        self, under_security_id, under_exchange_segment, expiry
    ) -> dict:
        """
        Retrieve the real-time Option Chain for a specified underlying instrument.

        :param under_security_id: The security ID of the underlying instrument.
        :type under_security_id: int
        :param under_exchange_segment: The exchange segment of the underlying instrument (e.g., NSE, BSE).
        :type under_exchange_segment: str
        :param expiry: The expiry date of the options.
        :type expiry: str

        """
        return await self.req.post(
            f"{self.base_url}/optionchain",
            data=json.dumps(
                dict(
                    UnderlyingScrip=under_security_id,
                    UnderlyingSeg=under_exchange_segment,
                    Expiry=expiry,
                )
            ),
            headers=self.headers_w_client_id,
        )

    async def expiry_list(
        self, under_security_id, under_exchange_segment
    ) -> dict:
        """
        Retrieve the dates of all expiries for a specified underlying instrument.

        :param under_security_id: The security ID of the underlying instrument.
        :type under_security_id: int
        :param under_exchange_segment: The exchange segment of the underlying instrument (e.g., NSE, BSE).
        :type under_exchange_segment: str

        """
        return await self.req.post(
            f"{self.base_url}/optionchain/expirylist",
            data=json.dumps(
                dict(
                    UnderlyingScrip=under_security_id,
                    UnderlyingSeg=under_exchange_segment,
                )
            ),
            headers=self.headers_w_client_id,
        )

    def convert_to_date_time(self, epoch) -> datetime:
        """
        Convert EPOCH time to Python datetime object in IST.

        :param epoch: The EPOCH time to convert.
        :type epoch: int

        """
        IST = timezone(timedelta(hours=5, minutes=30))
        dt = datetime.fromtimestamp(epoch, IST)

        if dt.time() == datetime.min.time():
            return dt.date()
        return dt
