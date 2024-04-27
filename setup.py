from setuptools import setup, find_packages
import pathlib

DIR = pathlib.Path(__file__).parent

setup(
    name="aio_trader",
    version="0.0.2",
    description="Async Python library for various Indian stock brokers.",
    long_description=(DIR / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="Benny Thadikaran",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Intended Audience :: Developers",
        "Intended Audience :: Financial and Insurance Industry",
        "Programming Language :: Python",
        "Natural Language :: English",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Libraries",
        "Programming Language :: Python :: 3 :: Only",
        "Operating System :: OS Independent",
    ],
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "aiodns==3.2.*",
        "aiohttp==3.9.*",
        "Brotli==1.1.*",
        "throttler==1.2.*",
    ],
    keywords="kite, kiteconnect, zerodha, algo-trading, stock-market, historical-data, intraday-data",
    project_urls={
        "Bug Reports": "https://github.com/BennyThadikaran/aio-trader/issues",
        "Source": "https://github.com/BennyThadikaran/aio-trader",
    },
)
