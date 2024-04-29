# Aio-Trader

An Async library for accessing Indian stockbroker API and real-time market feeds. 

Currently supports only Zerodha Kite (KiteConnect and Kite Web)

This Library is currently in Alpha. Expect breaking changes. Once testing is complete, I will release a pip package, and begin work on adding other brokers.

**Supports python 3.8+**

If you ❤️  my work so far, please 🌟 this repo.

## Documentation

https://bennythadikaran.github.io/Aio-Trader

API reference will be added in a day or two.

## Installation

**1. Clone the repo**

```bash
git clone https://github.com/BennyThadikaran/Aio-Trader.git

cd aio_trader
```

**2. Create a virtual env using `venv` and activate it.**

```bash
py -m venv .

source bin/activate

# On Windows, run the below to activate venv
.\Scripts\Activate.ps1
```

**3. Install aio_trader**

```bash
pip install .
```

**Note on Windows compatibility**

The `aio_dns` package requires SelectorEventLoop to work correctly. Import the `sys` module and add the below code, before any async code is run.

```python
if 'win' in sys.platform:
	asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

**Uvloop / Winloop**

[Uvloop](https://github.com/MagicStack/uvloop) is a fast, drop-in replacement for the default event loop. It only works on Linux/Mac. On Windows, you will need [Winloop](https://github.com/Vizonex/Winloop).

Once installed, you can add the below code after your imports. Replace `asyncio.run(main())` with `run(main())`

```python
if 'win' in sys.platform:
    from winloop import run
else:
    from uvloop import run
```

This setup works well with `aio_dns` no need to set an event loop policy on Windows.

## Differences between Aio-Trader and pykiteconnect (KiteConnect Official library)

| aio-trader | pykiteconnect |
|---|---|
| Uses aiohttp | Uses Twisted, an event-driven framework |
| Supports Python version 3.8+ | Supports Python version 2 & 3 |

Aio-Trader has fewer dependencies owing to its Python support.

KiteFeed uses the [python struct module](https://docs.python.org/3/library/struct.html) to parse binary data. It tries to unpack all values in a single function call, which is slightly more efficient.

You can also bypass parsing binary data if you want to use a custom parser.

```python
kws = KiteFeed(parse_data=False)
```

Another use case is to forward the data to the browser and parse it client-side. It avoids the overhead of serializing and deserializing the data.
