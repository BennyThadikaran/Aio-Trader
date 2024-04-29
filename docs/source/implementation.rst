======================
Package Implementation
======================

.. code:: bash

    aio_trader/
    ├── kite
    │   ├── Kite.py
    │   ├── KiteFeed.py
    │   └── __init__.py
    ├── AbstractBroker.py
    ├── AbstractFeeder.py
    ├── AsyncRequest.py
    ├── __init__.py
    └── utils.py

Each Stockbroker is packaged into a directory and can be imported independently of other brokers.

:py:obj:`aio_trader.kite` is the only package available now. I will be adding more soon.

.. code:: python

    from aio_trader.kite import Kite, KiteFeed

Kite.py
-------

:py:obj:`Kite.py` is used to make and manage orders, access profiles, holdings, etc.

The :py:obj:`Kite` class implements the :py:obj:`AbstractBroker` class.

:py:obj:`AsyncRequest` is responsible for making HTTP requests, handling errors, and returning the response. 

:py:obj:`AsyncRequest` has a mechanism for retrying requests in case of errors. It uses [exponential backoff](https://en.wikipedia.org/wiki/Exponential_backoff#Rate_limiting) to gradually increase the wait time between retries.

It starts with a 3-second wait after the first try and incrementally increases to a max wait of 30 seconds. See the simple implementation below. It is similar to [pykiteconnect](https://github.com/zerodha/pykiteconnect) implementation.

.. code:: python

    # incremental backoff
    base_wait = 3
    max_wait = 30
    retries = 0

    for i in range(1, 5):
        wait = min(base_wait * (2**retries), max_wait)
        retries += 1

        print(f"{retries} retry: {wait} seconds wait")

In case of any network error or HTTP status codes other than 200, the request is retried. The only exception is a RuntimeError, which closes the connection and raises the error.

The following status codes can trigger a RuntimeError:

- **400**: Incorrect method or params
- **429**: API Rate limit reached.
- **403**: Forbidden


KiteFeed.py
-----------

:py:obj:`KiteFeed.py` provides a WebSocket connection for receiving real-time market quotes.

KiteFeed implements the :py:obj:`AbstractFeeder` class. It has a similar retry mechanism to :py:obj:`Kite`. If there is an error, the connection is re-attempted. A response code of 403 indicates the session has expired or is invalid. The connection is closed, with no attempts to retry.

Utils.py
--------

Utils.py contains helper functions. It will be covered later.
