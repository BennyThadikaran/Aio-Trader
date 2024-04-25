# Aio-Trader

An Async library for accessing Indian stock broker API and Websockets. 

Currently supports only Zerodha Kite (KiteConnect and Kite Web)

Library is currently in Alpha stage. Once testing is completed, I will release a pip package and begin work on adding other brokers.

## Installation

**1. Clone the repo**

```bash
git clone https://github.com/BennyThadikaran/Aio-Trader.git

cd aio_trader
```

**2. Create virtual env using venv and activate it.**

```bash
py -m venv .

source bin/activate

# On windows
# source bin/activate.ps1
```

**3. Install aio_trader**

```bash
pip install .
```

## Kite api usage

**Kite Web login (Interactive prompt)** - Requires user_id, password and twofa.
To avoid interactive prompt, pass full or partial info to `kite.authorize`. Missing information will be prompted.

```python
# Kite Web Login Example 1
from aio_trader.kite import Kite
import asyncio


async def main():
    async with Kite() as kite:
        # Starts an interactive prompt for Kite Web login
        await kite.authorize()

        # Kite Web tokens are stored in cookies and reused on subsequent runs
        print(kite.enctoken)


asyncio.run(main())
```

When using a library like [pyotp](https://github.com/pyauth/pyotp), pass the function, to `kite.authorize` as below.

```python
import pyotp

totp = pyotp.TOTP('base32secret3232')
# totp.now() to get OTP

async with Kite() as kite:
    await kite.authorize(
        user_id=config["user_id"],
        password=config["password"],
        twofa=totp.now,
    )
```

**KiteConnect Login** - Requires api_key, request_token and api_secret.

```python
async with Kite(api_key=config['api_key']) as kite:
    await kite.authorize(
        request_token=config['request_token'],
        secret=config['secret']
    )

    # Can be stored and reused on subsequent runs
    print(kite.access_token)
```

## Kite Websocket usage

```python
from aio_trader.kite import KiteFeed
from aio_trader import utils
from typing import List
import asyncio


# Define handlers
def on_tick(tick: List, binary=False):
    print(tick)


def on_connect(kws: KiteFeed):
    print("connected")

    # Subscribe to Aarti Industries
    asyncio.create_task(kws.subscribe_symbols([1793]))


async def cleanup(kws):
    # perform clean up operations here
    await kws.close()


async def main():
    enctoken = "STORED_ENCTOKEN"
    user_id = "KITE_WEB_USER_ID"

    async with KiteFeed(
        user_id=user_id,
        enctoken=enctoken,
    ) as kws:
        kws.on_tick = on_tick
        kws.on_connect = on_connect

        # Handle KeyboardInterupt
        utils.add_signal_handlers(cleanup, kws)

        # No code executes after this line
        await kws.connect()


asyncio.run(main())
```

## More detailed documentation to follow soon
