=================
Complete Examples
=================

Handling Keyboard Interupt
--------------------------

Graceful exit on KeyboardInterupts

.. code:: python

    from aio_trader.kite import KiteFeed
    from aio_trader import utils
    from typing import List
    import asyncio, sys


    # Define handlers
    def on_tick(tick: List, binary=False):
        print(tick)


    def on_connect(kws: KiteFeed):
        print("connected")

        # Subscribe to Aarti Industries
        asyncio.create_task(kws.subscribe_symbols([1793]))


    def on_order_update(data: dict):
        # Store order data in database or other operations
        pass


    async def cleanup(kws, kite):
        # perform cleanup operations here
        await kws.close()
        await kite.close()


    async def main():

        await kite.authorize(
            request_token=request_token,
            api_key=api_key,
            secret=secret,
        )

        # Client session and logger instance are shared
        async with KiteFeed(
            user_id=user_id,
            enctoken=enctoken,
            session=kite.session
            logger=kite.log
        ) as kws:
            kws.on_tick = on_tick
            kws.on_connect = on_connect
            kws.on_order_update = on_order_update

            # Handle KeyboardInterupt
            utils.add_signal_handlers(cleanup, kws, kite)

            # No code executes after this line
            await kws.connect()


    # Credentials loaded from a database or JSON file
    enctoken = "STORED_ENCTOKEN"
    user_id = "KITE_WEB_USER_ID"

    # Defined globally to allow access across the script
    kite = Kite(access_token=access_token)

    if "win" in sys.platform:
      # Required for windows users
      asyncio.set_event_loop_policy(
          asyncio.WindowsSelectorEventLoopPolicy(),
      )

    asyncio.run(main())


Downloading historical data
---------------------------

When trying to download historical data synchronously, the typical approach would be:

1. Request historical data
2. Wait for a response from the server
3. Process the data
4. Repeat in a loop for the remaining symbols.

The process is blocked while waiting for the server's response. No other task is executed, during this time.

**With Async,**

1. I am iterating over the symbols, creating a :py:obj:`Task` for each request.
2. The :py:obj:`Task` does not execute the request immediately. Instead, it is scheduled for concurrent execution.
3. Once the :py:obj:`Task` executes, it does not wait for the server response. It yields control back to the event loop to run other tasks.
4. As the response returns, the :py:obj:`Task` is marked completed, and the result is available for processing. It eliminates a lot of time waiting on the network.

Long CPU-intensive or IO-bound tasks can block the event loop. Use :py:obj:`loop.run_in_executor` to execute functions in separate threads or processes, without blocking the event loop.

.. code:: python

    from aio_trader.kite import Kite
    from aio_trader import utils
    from pathlib import Path
    from typing import List
    import pandas as pd, asyncio


    async def main():
        DIR = Path(__file__).parent
        instruments_file = DIR / "nse_instruments.csv"

        sym_list = (
            "AARTIIND",
            "ASIANPAINT",
            "BATAINDIA",
            "HDFCLIFE",
            "BLUEDART",
            "BRITANNIA",
            "DEEPAKFERT",
            "DRREDDY",
            "EICHERMOT",
            "EIDPARRY",
        )

        columns = ("Date", "Open", "High", "Low", "Close", "Volume")

        async with Kite() as kite:
            await kite.authorize()

            if not instruments_file.exists():
                instruments_file.write_bytes(
                    await kite.instruments(exchange=kite.EXCHANGE_NSE)
                )

            df = pd.read_csv(instruments_file, index_col="tradingsymbol")
            tasks: List[asyncio.Task] = []

            for sym in sym_list:
                # An async function returns a coroutine unless awaited
                coroutine = kite.historical_data(
                    df.loc[sym, "instrument_token"],
                    from_dt="2024-04-22",
                    to_dt="2024-04-26",
                    interval="day",
                )

                # Assign the coroutine to a task, to schedule it for execution
                # in the event loop.
                # Here the task name is assigned the symbol name.
                # We can use task.get_name to return this value
                task = asyncio.create_task(coroutine, name=sym)

                tasks.append(task)

            # asyncio.as_completed returns a coroutine with no reference to the task.
            # utils.as_completed returns the original task object from the previous
            # step.
            async for task in utils.as_completed(tasks):
                sym_name = task.get_name()
                result = task.result()

                candles = result["data"]["candles"]

                df = pd.DataFrame(candles, columns=columns, copy=False)

                df["Date"] = pd.to_datetime(df["Date"])
                df.set_index("Date", drop=True, inplace=True)

                # save the result or perform further processing


    asyncio.run(main())
