# MarketPulse - Real-Time Trading Simulator

A fully self-contained Django demonstration project: a live stock-trading
simulator with a **backend-heavy architecture** and an **interactive trading
terminal** frontend. No external services - just SQLite and the standard
library. Everything (market simulation, order matching, bot traders) runs
in-process from `runserver`.

![stack](https://img.shields.io/badge/Django-5.1-092E20) ![drf](https://img.shields.io/badge/DRF-3.x-A30000) ![db](https://img.shields.io/badge/DB-SQLite%20(WAL)-003B57)

## What it does

- **Live market engine** - a daemon thread advances every instrument's price
  on a fixed interval using a Gaussian random walk (with occasional "news"
  spikes), persisting a `PriceTick` time series.
- **Order-execution engine** - market & limit orders, weighted-average cost
  basis, realized/unrealized P&L, resting limit-order matching, and validation
  (insufficient funds/shares). All trade mutations are serialized with a
  process-wide lock + DB transactions so the background thread and web
  requests never corrupt a balance.
- **Bot traders** - seeded bot portfolios trade randomly each tick to keep the
  tape and leaderboard alive during a demo.
- **REST API** (Django REST Framework) - instruments, price history, portfolio,
  orders, trades, leaderboard, and a live engine heartbeat.
- **Interactive terminal UI** - a dark trading dashboard with a custom
  canvas price chart (no JS libraries / CDNs), a live ticker tape, watchlist,
  order ticket, portfolio panel, and a leaderboard - all polling the API.
- **Auth** - login / signup; new users are auto-provisioned a funded portfolio
  via a signal. Full Django admin over every model.

## Architecture

```
marketpulse/          project config (settings, urls, api_urls, wsgi/asgi)
market/               instruments + price ticks + the simulation engine
  engine.py           ← background random-walk price engine (daemon thread)
  apps.py             ← SQLite WAL setup + engine autostart
trading/              portfolios, holdings, orders, trades
  services.py         ← the order-execution / matching engine (core logic)
  signals.py          ← auto-create a portfolio per new user
dashboard/            auth views + the terminal page
templates/ static/    frontend (HTML + CSS + vanilla-JS canvas charting)
```

## Quick start

```bash
python -m venv venv
venv\Scripts\activate            # Windows  (use: source venv/bin/activate on *nix)
pip install -r requirements.txt

python manage.py migrate
python manage.py seed            # instruments, price history, demo user, bots
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and sign in:

| Account | Username | Password     |
|---------|----------|--------------|
| Demo    | `demo`   | `demo12345`  |
| Admin   | `admin`  | `admin12345` |

The market starts moving the moment `runserver` is up. Watch the ticker tick,
place buy/sell orders, rest a limit order and watch it fill, and climb the
leaderboard against the bots.

> Re-seed from scratch any time with `python manage.py seed --reset`.

## REST API

All endpoints require an authenticated session. Browse them interactively via
DRF's browsable API.

| Method | Endpoint                              | Purpose                       |
|--------|---------------------------------------|-------------------------------|
| GET    | `/api/instruments/`                   | List instruments + live price |
| GET    | `/api/instruments/{symbol}/history/`  | Price-tick history            |
| GET    | `/api/market/status/`                 | Engine heartbeat              |
| GET    | `/api/portfolio/`                     | Cash, equity, P&L, holdings   |
| GET/POST | `/api/orders/`                      | List / place orders           |
| POST   | `/api/orders/{id}/cancel/`            | Cancel a resting order        |
| GET    | `/api/trades/`                        | Executed trade tape           |
| GET    | `/api/leaderboard/`                   | Ranked portfolios             |

Example - place a market buy:

```bash
curl -X POST http://127.0.0.1:8000/api/orders/ \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","side":"BUY","order_type":"MARKET","quantity":10}'
```

## Notable backend details

- **SQLite in WAL mode** (`PRAGMA journal_mode=WAL`) so the engine thread can
  write ticks while requests read concurrently; `busy_timeout` smooths
  contention.
- **Engine autostart guard** - the simulation only launches in the live
  `runserver` worker (`RUN_MAIN == "true"`), never the autoreload watcher or
  during management commands.
- **Decimal money** everywhere persisted; float only inside the random walk,
  with a single `to_money()` conversion boundary.
- **Local-memory caching** for the market snapshot and leaderboard.
- Run the engine standalone (e.g. under gunicorn) with
  `python manage.py run_market`.

## Configuration

Tune the simulation in `marketpulse/settings.py → MARKET_ENGINE`:

```python
MARKET_ENGINE = {
    "AUTOSTART": True,
    "TICK_INTERVAL": 1.5,        # seconds between price ticks
    "STARTING_CASH": 100_000.0,  # new-account balance
    "MAX_HISTORY_TICKS": 600,    # history retained per instrument
}
```
