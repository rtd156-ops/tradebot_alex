"""Clientes de ejecución del modo multi-estrategia.

A diferencia de los brokers single-strategy, estos clientes NO conocen
estrategias ni posiciones: solo ejecutan órdenes de mercado y reportan la
wallet. La separación lógica vive en el ledger; aquí solo se etiqueta cada
orden con su order_link_id (en Bybit viaja como orderLinkId, visible en el
historial del exchange para auditoría).
"""
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass

log = logging.getLogger(__name__)

PAPER_WALLET_FILE = "data/state/paper_wallet.json"


def make_order_link_id(strategy_id: str, symbol: str) -> str:
    """Identificador por orden: estrategia + símbolo + timestamp + uuid.
    Bybit acepta hasta 36 caracteres alfanuméricos, '-' y '_'."""
    base = symbol.split("/")[0]
    return f"{strategy_id[:8]}-{base[:5]}-{int(time.time()) % 10**8}-{uuid.uuid4().hex[:6]}"


@dataclass
class Fill:
    qty: float
    price: float
    cost: float      # USD totales que salieron (compra) o entraron (venta), con comisión


class PaperExecution:
    """Wallet simulada compartida (USDT + monedas), persistida en JSON.
    Reproduce el mismo flujo que Bybit para que la reconciliación del
    allocator se ejercite igual que en live."""

    def __init__(self, starting_cash: float = 10000, fee_pct: float = 0.001,
                 wallet_file: str = PAPER_WALLET_FILE):
        self.fee_pct = fee_pct
        self.wallet_file = wallet_file
        self.wallet = self._load() or {"USDT": float(starting_cash)}

    def _load(self):
        if os.path.exists(self.wallet_file):
            try:
                with open(self.wallet_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                log.warning("No se pudo leer la wallet simulada: %s", e)
        return None

    def _save(self):
        os.makedirs(os.path.dirname(self.wallet_file), exist_ok=True)
        with open(self.wallet_file, "w", encoding="utf-8") as f:
            json.dump(self.wallet, f, indent=2)

    def fetch_balances(self) -> dict[str, float]:
        return dict(self.wallet)

    def market_buy(self, symbol: str, usd_amount: float, price: float,
                   order_link_id: str) -> Fill | None:
        cost = usd_amount * (1 + self.fee_pct)
        if cost > self.wallet.get("USDT", 0):
            log.warning("[PAPER] USDT insuficiente para %s (%s)", symbol, order_link_id)
            return None
        qty = usd_amount / price
        base = symbol.split("/")[0]
        self.wallet["USDT"] -= cost
        self.wallet[base] = self.wallet.get(base, 0) + qty
        self._save()
        log.info("[PAPER] BUY %s qty=%.8f @ %.2f (%s)", symbol, qty, price, order_link_id)
        return Fill(qty=qty, price=price, cost=cost)

    def market_sell(self, symbol: str, qty: float, price: float,
                    order_link_id: str) -> Fill | None:
        base = symbol.split("/")[0]
        if qty > self.wallet.get(base, 0) + 1e-12:
            log.warning("[PAPER] %s insuficiente para vender (%s)", base, order_link_id)
            return None
        proceeds = qty * price * (1 - self.fee_pct)
        self.wallet[base] -= qty
        if self.wallet[base] < 1e-12:
            del self.wallet[base]
        self.wallet["USDT"] = self.wallet.get("USDT", 0) + proceeds
        self._save()
        log.info("[PAPER] SELL %s qty=%.8f @ %.2f (%s)", symbol, qty, price, order_link_id)
        return Fill(qty=qty, price=price, cost=proceeds)


class BybitExecution:
    """Órdenes spot reales en Bybit (testnet o mainnet) con orderLinkId."""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True,
                 fee_pct: float = 0.001):
        if not api_key or not api_secret:
            raise ValueError("Faltan BYBIT_API_KEY / BYBIT_API_SECRET en el .env")
        import ccxt
        self.fee_pct = fee_pct
        self.exchange = ccxt.bybit({
            "apiKey": api_key, "secret": api_secret,
            "enableRateLimit": True, "options": {"defaultType": "spot"},
        })
        if testnet:
            self.exchange.set_sandbox_mode(True)
            log.info("BybitExecution en modo TESTNET")

    def fetch_balances(self) -> dict[str, float]:
        balance = self.exchange.fetch_balance()
        free = balance.get("free", {}) or {}
        return {asset: float(amount or 0) for asset, amount in free.items()}

    def market_buy(self, symbol: str, usd_amount: float, price: float,
                   order_link_id: str) -> Fill | None:
        try:
            qty = usd_amount / price
            order = self.exchange.create_order(
                symbol, "market", "buy", qty, None, {"orderLinkId": order_link_id})
            fill_price = float(order.get("average") or price)
            fill_qty = float(order.get("filled") or qty)
            cost = float(order.get("cost") or usd_amount) * (1 + self.fee_pct)
            log.info("[LIVE] BUY %s id=%s link=%s", symbol, order.get("id"), order_link_id)
            return Fill(qty=fill_qty, price=fill_price, cost=cost)
        except Exception as e:
            log.error("Error al comprar %s (%s): %s", symbol, order_link_id, e)
            return None

    def market_sell(self, symbol: str, qty: float, price: float,
                    order_link_id: str) -> Fill | None:
        try:
            order = self.exchange.create_order(
                symbol, "market", "sell", qty, None, {"orderLinkId": order_link_id})
            fill_price = float(order.get("average") or price)
            fill_qty = float(order.get("filled") or qty)
            proceeds = float(order.get("cost") or fill_qty * fill_price) * (1 - self.fee_pct)
            log.info("[LIVE] SELL %s id=%s link=%s", symbol, order.get("id"), order_link_id)
            return Fill(qty=fill_qty, price=fill_price, cost=proceeds)
        except Exception as e:
            log.error("Error al vender %s (%s): %s", symbol, order_link_id, e)
            return None
