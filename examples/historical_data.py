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
