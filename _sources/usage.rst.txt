=====
Usage
=====

You can import the modules you require as below

.. code:: python

    from aio_trader.kite import Kite, KiteFeed
    from aio_trader.fyers import Fyers, FyersFeed, FyersOrder, FyersAuth
    from aio_trader.dhan import Dhan, DhanFeed, DhanOrder

    from aio_trader import utils # Helper functions

`Kite`, `Fyers` and `Dhan` allow making requests to the brokers api.

`KiteFeed`, `FyersFeed`, and `DhanFeed` provides a WebSocket connection to receive real-time market quotes and order updates.

With async context manager
--------------------------

**Broker API**

.. code:: python

    async with Kite() as kite:
      await kite.authorize()


**Market Feed**

.. code:: python

    async with KiteFeed(user_id=user_id, enctoken=enctoken) as kws:

      # No code executes after this line
      await Kws.connect()

Without context manager
-----------------------

**Broker API**

.. code:: python

    kite = Kite()
    await kite.authorize() # Required only for Kite
    
    # Close session once done
    kite.close()

**Market Feed**

.. code:: python

    kws = KiteFeed(api_key=api_key, access_token=access_token)

    # No code executes after this line
    await kws.connect()

Event handlers
--------------

Both the Market feed and Order feed class accept optional handlers. You may define them as per your needs.

**NOTE:** `on_tick` is necessary and must be attached for both Market and Order feed.

.. code:: python

    def on_tick(kws: KiteFeed, tick: List, binary=False):
      # To receive market quotes
      pass

    def on_connect(kws: KiteFeed):
      # Notify when WebSockets connection established
      pass

    def on_order_update(kws: KiteFeed, data: dict):
      # Notify on order updates
      pass

    def on_error(kws: KiteFeed, reason: str):
      # Notify on error
      pass

    def on_message(kws: KiteFeed, msg: str):
      # Other text messages or alerts
      pass

    with KiteFeed(user_id=user_id, enctoken=enctoken) as kws:
      kws.on_tick = on_tick
      kws.on_connect = on_connect
      kws.on_order_update = on_order_update
      kws.on_error = on_error

      await kws.connect()

Get Raw Binary data
-------------------

If you wish to receive the raw binary data from the WebSocket connection, you can set the **parse_data** argument of :py:obj:`KiteFeed` to :py:obj:`False`.

.. code:: python

    kws = KiteFeed(parse_data=False)

You may want to use a custom binary parser or forward the data to the browser and parse it client-side. It avoids the overhead of serializing and deserializing the data.

Session Sharing
---------------

The broker, marketfeed and orderfeed all store an instance of :py:obj:`aiohttp.ClientSession`. A session allows sharing of cookies and maintains a connection pool, to be reused between HTTP requests. It speeds up requests by not having to reestablish secure connections.

You can access the session object with :py:obj:`Kite.session` and :py:obj:`KiteFeed.session`.

A session, can be shared by passing it during initialization.

.. code:: python
    
    kite = Kite()

    kws = KiteFeed(session=kite.session)

Logging
-------

Aio-Trader uses the Python `logging` module to output logs. You must define the basic configuration for logging to enable it.

.. code:: python

  import logging

  logging.basicConfig(
      format="%(levelname)s: %(asctime)s - %(name)s - %(message)s",
      datefmt="%d-%m-%Y %H:%M",
      level=logging.INFO,
  )
