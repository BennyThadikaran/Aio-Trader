# Aio-Trader

An Async library for accessing Indian stockbroker API and real-time market feeds.

Supported brokers:

- Zerodha Kite (KiteConnect and Kite Web),
- DhanHQ (API, Real-Time market & Order feeds),
- Fyers (API, Real-Time market & Order feeds)

This library uses [aiohttp](https://docs.aiohttp.org/en/stable/index.html) for both HTTP requests and websockets.

Having the same dependencies across all brokers, ensures the same basic setup and predictable error handling. The library allows flexible application design whether running in the main event loop or multithreaded.

While the basic setup is the same for all brokers, the API methods and their signatures, mimic the official implementation.

In the future, it might be possible to add an Adapter class to smooth out differences between the brokers.

This Library is currently in Alpha. Expect breaking changes. Once testing is complete, I will release a pip package, and begin work on adding other brokers.

**Supports python 3.8+**

If you ❤️ my work so far, please 🌟 this repo.

## Documentation

https://bennythadikaran.github.io/Aio-Trader

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
