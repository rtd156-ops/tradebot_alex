"""Ledger SQLite: la fuente de verdad local del modo multi-estrategia.

Mantiene la separación lógica de capital y posiciones por estrategia sobre
una wallet compartida. Toda mutación queda registrada (órdenes, trades,
señales, eventos), por lo que el estado es auditable y sobrevive reinicios.

Decisión de diseño: el cash lógico de cada estrategia se inicializa con su
capital_limit_usd. Si el límite cambia en la config, la diferencia se aplica
al cash (y queda registrada como evento 'capital_adjusted'); las posiciones
abiertas no se tocan.
"""
import logging
import os
import sqlite3
from datetime import datetime, timezone

log = logging.getLogger(__name__)

DEFAULT_PATH = "data/state/ledger.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies(
    strategy_id TEXT PRIMARY KEY,
    capital_limit_usd REAL NOT NULL,
    cash REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions(
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    qty REAL NOT NULL,
    entry_price REAL NOT NULL,
    cost REAL NOT NULL,
    order_link_id TEXT,
    opened_at TEXT NOT NULL,
    peak_price REAL,
    PRIMARY KEY(strategy_id, symbol)
);
CREATE TABLE IF NOT EXISTS orders(
    order_link_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    qty REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    pnl REAL NOT NULL,
    reason TEXT NOT NULL,
    opened_at TEXT,
    closed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signals(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    score REAL,
    price REAL,
    executed INTEGER NOT NULL,
    reject_reason TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    strategy_id TEXT,
    detail TEXT,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self, path: str = DEFAULT_PATH):
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        """Migraciones de esquema para bases creadas por versiones anteriores."""
        columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(positions)")}
        if "peak_price" not in columns:
            self.conn.execute("ALTER TABLE positions ADD COLUMN peak_price REAL")
            self.conn.execute("UPDATE positions SET peak_price=entry_price")
            log.info("Migración: columna peak_price agregada a positions")

    # --- Estrategias y cash ---
    def ensure_strategy(self, strategy_id: str, capital_limit_usd: float):
        row = self.conn.execute(
            "SELECT capital_limit_usd, cash FROM strategies WHERE strategy_id=?",
            (strategy_id,)).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO strategies VALUES (?,?,?,?)",
                (strategy_id, capital_limit_usd, capital_limit_usd, _now()))
        elif abs(row["capital_limit_usd"] - capital_limit_usd) > 1e-9:
            delta = capital_limit_usd - row["capital_limit_usd"]
            self.conn.execute(
                "UPDATE strategies SET capital_limit_usd=?, cash=cash+? WHERE strategy_id=?",
                (capital_limit_usd, delta, strategy_id))
            self.record_event("capital_adjusted", strategy_id,
                              f"límite {row['capital_limit_usd']} -> {capital_limit_usd}")
        self.conn.commit()

    def cash(self, strategy_id: str) -> float:
        row = self.conn.execute(
            "SELECT cash FROM strategies WHERE strategy_id=?", (strategy_id,)).fetchone()
        return float(row["cash"]) if row else 0.0

    def capital_limit(self, strategy_id: str) -> float:
        row = self.conn.execute(
            "SELECT capital_limit_usd FROM strategies WHERE strategy_id=?",
            (strategy_id,)).fetchone()
        return float(row["capital_limit_usd"]) if row else 0.0

    def total_cash(self) -> float:
        row = self.conn.execute("SELECT COALESCE(SUM(cash),0) AS t FROM strategies").fetchone()
        return float(row["t"])

    # --- Posiciones ---
    def open_position(self, strategy_id: str, symbol: str, qty: float,
                      entry_price: float, cost: float, order_link_id: str):
        """Transacción: descuenta el cash y registra posición + orden."""
        cash = self.cash(strategy_id)
        if cost > cash + 1e-9:
            raise ValueError(f"cash insuficiente en {strategy_id}: {cost:.2f} > {cash:.2f}")
        with self.conn:
            self.conn.execute(
                "UPDATE strategies SET cash=cash-? WHERE strategy_id=?", (cost, strategy_id))
            self.conn.execute(
                "INSERT INTO positions VALUES (?,?,?,?,?,?,?,?)",
                (strategy_id, symbol, qty, entry_price, cost, order_link_id,
                 _now(), entry_price))
            self.conn.execute(
                "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
                (order_link_id, strategy_id, symbol, "buy", qty, entry_price,
                 "filled", _now()))

    def close_position(self, strategy_id: str, symbol: str, exit_price: float,
                       proceeds: float, reason: str, order_link_id: str) -> float:
        """Transacción: vende SOLO la posición lógica de esta estrategia.
        Devuelve el PnL realizado (proceeds netos - costo de entrada)."""
        pos = self.position(strategy_id, symbol)
        if pos is None:
            raise ValueError(f"{strategy_id} no tiene posición en {symbol}")
        pnl = proceeds - pos["cost"]
        with self.conn:
            self.conn.execute(
                "UPDATE strategies SET cash=cash+? WHERE strategy_id=?",
                (proceeds, strategy_id))
            self.conn.execute(
                "DELETE FROM positions WHERE strategy_id=? AND symbol=?",
                (strategy_id, symbol))
            self.conn.execute(
                "INSERT INTO trades(strategy_id,symbol,qty,entry_price,exit_price,"
                "pnl,reason,opened_at,closed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (strategy_id, symbol, pos["qty"], pos["entry_price"], exit_price,
                 pnl, reason, pos["opened_at"], _now()))
            self.conn.execute(
                "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
                (order_link_id, strategy_id, symbol, "sell", pos["qty"], exit_price,
                 "filled", _now()))
        return pnl

    def position(self, strategy_id: str, symbol: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM positions WHERE strategy_id=? AND symbol=?",
            (strategy_id, symbol)).fetchone()
        return dict(row) if row else None

    def positions(self, strategy_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM positions WHERE strategy_id=?", (strategy_id,)).fetchall()
        return [dict(r) for r in rows]

    def total_qty_by_symbol(self) -> dict[str, float]:
        rows = self.conn.execute(
            "SELECT symbol, SUM(qty) AS q FROM positions GROUP BY symbol").fetchall()
        return {r["symbol"]: float(r["q"]) for r in rows}

    def update_peak(self, strategy_id: str, symbol: str, price: float):
        """Sube el precio pico de la posición (nunca baja), para el trailing stop."""
        self.conn.execute(
            "UPDATE positions SET peak_price=MAX(COALESCE(peak_price, entry_price), ?) "
            "WHERE strategy_id=? AND symbol=?", (price, strategy_id, symbol))
        self.conn.commit()

    # --- Consultas para protecciones (cooldown, stoploss guard, drawdown) ---
    def last_close_time(self, strategy_id: str, symbol: str) -> str | None:
        row = self.conn.execute(
            "SELECT MAX(closed_at) AS t FROM trades WHERE strategy_id=? AND symbol=?",
            (strategy_id, symbol)).fetchone()
        return row["t"]

    def stop_losses_since(self, strategy_id: str, since_iso: str) -> tuple[int, str | None]:
        """(número de stops en la ventana, timestamp del último stop)."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS n, MAX(closed_at) AS last FROM trades "
            "WHERE strategy_id=? AND reason IN ('stop_loss','trailing_stop') "
            "AND closed_at >= ?", (strategy_id, since_iso)).fetchone()
        return int(row["n"]), row["last"]

    def pnls_since(self, strategy_id: str, since_iso: str) -> list[float]:
        rows = self.conn.execute(
            "SELECT pnl FROM trades WHERE strategy_id=? AND closed_at >= ? ORDER BY id",
            (strategy_id, since_iso)).fetchall()
        return [float(r["pnl"]) for r in rows]

    # --- Métricas y auditoría ---
    def buys_today(self, strategy_id: str) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM orders WHERE strategy_id=? AND side='buy' "
            "AND created_at LIKE ?", (strategy_id, f"{today}%")).fetchone()
        return int(row["n"])

    def trades(self, strategy_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE strategy_id=? ORDER BY id", (strategy_id,)).fetchall()
        return [dict(r) for r in rows]

    def record_signal(self, strategy_id: str, symbol: str, action: str, score: float,
                      price: float, executed: bool, reject_reason: str | None = None):
        self.conn.execute(
            "INSERT INTO signals(strategy_id,symbol,action,score,price,executed,"
            "reject_reason,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (strategy_id, symbol, action, score, price, int(executed),
             reject_reason, _now()))
        self.conn.commit()

    def record_event(self, type_: str, strategy_id: str | None, detail: str):
        self.conn.execute(
            "INSERT INTO events(type,strategy_id,detail,created_at) VALUES (?,?,?,?)",
            (type_, strategy_id, detail, _now()))
        self.conn.commit()

    def signal_counts(self, strategy_id: str) -> dict:
        rows = self.conn.execute(
            "SELECT action, COUNT(*) AS n FROM signals WHERE strategy_id=? GROUP BY action",
            (strategy_id,)).fetchall()
        return {r["action"]: int(r["n"]) for r in rows}

    def reject_counts(self, strategy_id: str) -> dict:
        rows = self.conn.execute(
            "SELECT reject_reason, COUNT(*) AS n FROM signals WHERE strategy_id=? "
            "AND reject_reason IS NOT NULL GROUP BY reject_reason",
            (strategy_id,)).fetchall()
        return {r["reject_reason"]: int(r["n"]) for r in rows}

    def close(self):
        self.conn.close()
