==============
Implementation
==============

:py:obj:`Aio-Trader` library comes with 3 packages: 

- :py:obj:`aio_trader.kite`

  - :py:obj:`aio_trader.kite.Kite` : Class for making API requests
  - :py:obj:`aio_trader.kite.KiteFeed` : Websockets class for real time stock data.

- :py:obj:`aio_trader.fyers`

  - :py:obj:`aio_trader.fyers.Fyers` : Class for making API requests
  - :py:obj:`aio_trader.fyers.FyersFeed` : Websockets class for real time stock data.
  - :py:obj:`aio_trader.fyers.FyersOrder` : Websockets class for order notifications.

- :py:obj:`aio_trader.dhan`

  - :py:obj:`aio_trader.dhan.Dhan` : Class for making API requests
  - :py:obj:`aio_trader.dhan.DhanFeed` : Websockets class for real time stock data.
  - :py:obj:`aio_trader.dhan.DhanOrder` : Websockets class for order notifications.

There are also helper classes.

- :py:obj:`aio_trader.AsyncRequest` : Class for making HTTP requests, handling errors and processing the response.

  - AsyncRequest has a mechanism for retrying requests in case of errors. 
    It uses `exponential backoff <https://en.wikipedia.org/wiki/Exponential_backoff#Rate_limiting>`_ to gradually increase the wait time between retries.

- :py:obj:`aio_trader.utils` : Contains helper functions.

The broker class like Kite, implement the :py:obj:`aio_trader.AbstractBroker`

The market feed (FyersFeed), and order feeds (FyersOrder), implement the :py:obj:`aio_trader.AbstractFeeder`

