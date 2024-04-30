==========
Kite Usage
==========

:py:obj:`Aio-Trader` contains the :py:obj:`aio_trader.kite` package and :py:obj:`aio_trader.utils` module.

:py:obj:`aio_trader.kite` package comes with 2 modules - :py:obj:`Kite` and :py:obj:`KiteFeed`.

You can import them as 

.. code:: python

    from aio_trader.kite import Kite, KiteFeed
    from aio_trader import utils

kite.Kite
=========

:py:obj:`Kite` provides methods for managing orders, accessing profiles, and getting historical market data and quotes.

With async context manager
--------------------------

.. code:: python

    async with Kite() as kite:
      await kite.authorize()

Without context manager
-----------------------

.. code:: python

    kite = Kite()
    await kite.authorize()
    
    # Close session
    kite.close()


Kite Login and authorization
----------------------------

All arguments are optional. It defaults to Kite web login if no arguments are provided. You will be required to enter your credentials via terminal user input.

Once authorization is complete, the token is set. You can access them as 

- :py:obj:`kite.enctoken` - For Kite web login 
- :py:obj:`kite.access_token` - For KiteConnect login

These can be stored or saved and reused on the next run. You can pass the token to the Kite class during initialization.

**For Kite web login**, :py:obj:`Kite.authorize` takes the following optional parameters:

- :py:obj:`user_id`: Kite Web user-id
- :py:obj:`password`: Kite Web login password
- :py:obj:`twofa`: string or callable function that returns OTP

To generate OTP you can use a package like `pyotp <https://pypi.org/project/pyotp/>`_, just pass :py:obj:`totp.now` to **twofa** argument.

.. code:: python

    # Kite Web Login
    async with Kite(enctoken=enctoken) as kite:
      await kite.authorize(
          user_id=user_id,
          password=pwd,
          twofa="123124",
      )

**For KiteConnect login**, :py:obj:`Kite.authorize` takes the following optional parameters:

- :py:obj:`request_token` : KiteConnect request_token 
- :py:obj:`api_key`: KiteConnect API key
- :py:obj:`secret`: KiteConnect API secret

.. code:: python

    # KiteConnect login
    async with Kite(access_token=access_token) as kite:
      await kite.authorize(
          request_token=request_token,
          api_key=api_key,
          secret=secret,
      )

kite.KiteFeed
=============

:py:obj:`KiteFeed` provides a WebSocket connection to receive real-time market quotes and order updates.

With async context manager
--------------------------

.. code:: python

    async with KiteFeed(user_id=user_id, enctoken=enctoken) as kws:

      # No code executes after this line
      await Kws.connect()

Without context manager
-----------------------

It is important to close WebSocket connections and Client Session before exiting the application.

In the below example, :py:obj:`kws.close` will not be executed. However, it is shown here for completeness.

.. code:: python

    kws = KiteFeed(api_key=api_key, access_token=access_token)

    # No code executes after this line
    await kws.connect()
    
    # Close Unsubscribe instruments, close WebSocket connection, and session
    kws.close()

KiteFeed requires the following optional arguments

**For Kite Web:**

- :py:obj:`user_id`: Kite Web user-id
- :py:obj:`enctoken`: enctoken obtained from Kite Web Login

**For KiteConnect:**

- :py:obj:`api_key`: Kite Web user-id
- :py:obj:`access_token` : access_token obtained from KiteConnect login

Event handlers
--------------

The :py:obj:`KiteFeed` class accepts the below optional handlers. You may define them as per your needs.

.. code:: python

    def on_tick(tick: List, binary=False):
      # To receive market quotes
      pass

    def on_connect(kws: KiteFeed):
      # Notify when WebSockets connection established
      pass

    def on_order_update(data: dict):
      # Notify on order updates
      pass

    def on_error(kws: KiteFeed, reason: str):
      # Notify on error
      pass

    def on_message(msg: str):
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

Authorization Flow
==================

1. On running :py:obj:`Kite.authorize`, it first checks if :py:obj:`enctoken` or :py:obj:`access_token` was set during initialization. 
    - If yes, the authorization headers are updated, and the class is ready to make API requests. 
2. If :py:obj:`request_token` and :py:obj:`secret` are provided, proceed with KiteConnect login. Once the :py:obj:`access_token` is received, set the authorization headers.
3. For Kite Web login, :py:obj:`enctoken` is stored in cookies. Check if the cookie file exists and has not expired. If yes, load the :py:obj:`enctoken` and update headers.
4. If no cookie file exists or has expired, proceed with Kite Web login. Once the :py:obj:`enctoken` is received:
    - Set the cookie expiry for the end of the day.
    - Save the cookie to file
    - Update the authorization headers with :py:obj:`enctoken`

Session Sharing
===============

Both :py:obj:`Kite` and :py:obj:`KiteFeed` store an instance of :py:obj:`aiohttp.ClientSession`. A session allows sharing of cookies and maintains a connection pool, to be reused between HTTP requests. It speeds up requests by not having to reestablish secure connections.

You can access the session object with :py:obj:`Kite.session` and :py:obj:`KiteFeed.session`.

A Kite session, can be shared with KiteFeed by passing it during initialization.

.. code:: python
    
    kite = Kite()

    kws = KiteFeed(session=kite.session)

Logging
=======

Aio-Trader uses the Python `logging` module to output logs. You can define your logger and pass the instance to :py:obj:`Kite` and :py:obj:`KiteFeed`.

.. code:: python
    
    kite = Kite(logger=logger)

    # Share the same logger instance
    kws = KiteFeed(logger=kite.log)

Alternatively, the :py:obj:`aio_trader.utils` module provides a helper function :py:obj:`configure_default_logger`. It takes an optional name argument, which defaults to `aio_trader` and returns a configured logger instance of that name.

.. code:: python

    from aio_trader.utils import configure_default_logger 
    import logging
   
    # Returns a logging.Logger instance of name aio_trader
    logger = configure_default_logger('aio_trader')

    # Default level is INFO
    logger.setLevel(logging.WARNING)

    kite = Kite(logger=logger)
