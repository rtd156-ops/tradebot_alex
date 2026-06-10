"""Allocator / risk manager central del modo multi-estrategia.

Responsabilidades:
- Calcular el tamaño de posición de cada estrategia con base en SU capital.
- Validar cada compra: capital propio, límite diario, posición duplicada,
  mínimo de orden y que el total no exceda el balance real de la wallet.
- Reconciliar el ledger lógico contra la wallet real: si el ledger reclama
  más cash o más monedas de las que existen, bloquea TODA ejecución (compras
  y ventas) hasta intervención humana. Decisión documentada en README.

Es determinista: mismas entradas -> mismas decisiones, y cada rechazo
devuelve un motivo explícito que queda registrado en el ledger.
"""
import logging

from .ledger import Ledger

log = logging.getLogger(__name__)

MIN_ORDER_USD = 10.0
# Tolerancia de reconciliación: comisiones y redondeos de qty del exchange
TOLERANCE_PCT = 0.02
TOLERANCE_ABS = 1.0


class Allocator:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self.blocked = False
        self.block_reasons: list[str] = []

    # --- Reconciliación contra la wallet real ---
    def reconcile(self, real_balances: dict[str, float]) -> list[str]:
        """Compara el ledger contra la wallet. La wallet puede tener MÁS que
        el ledger (fondos no gestionados); nunca menos."""
        problems = []
        real_usdt = float(real_balances.get("USDT", 0))
        ledger_cash = self.ledger.total_cash()
        if ledger_cash > real_usdt * (1 + TOLERANCE_PCT) + TOLERANCE_ABS:
            problems.append(
                f"cash lógico {ledger_cash:.2f} USDT > real {real_usdt:.2f} USDT")
        for symbol, qty in self.ledger.total_qty_by_symbol().items():
            base = symbol.split("/")[0]
            real_qty = float(real_balances.get(base, 0))
            if qty > real_qty * (1 + TOLERANCE_PCT) + 1e-8:
                problems.append(
                    f"{symbol}: ledger {qty:.8f} {base} > wallet {real_qty:.8f} {base}")
        self.blocked = bool(problems)
        self.block_reasons = problems
        if problems:
            log.error("RECONCILIACIÓN FALLIDA, ejecución bloqueada: %s", problems)
            self.ledger.record_event("risk_block", None, "; ".join(problems))
        return problems

    # --- Decisiones de compra ---
    def position_size(self, strategy_cfg) -> float:
        """USD para una nueva posición: % del capital asignado (fijo y
        determinista), acotado por el cash lógico disponible."""
        max_pct = strategy_cfg.portfolio.get("max_position_pct", 0.15)
        cash = self.ledger.cash(strategy_cfg.strategy_id)
        return min(strategy_cfg.capital_limit_usd * max_pct, cash * 0.98)

    def check_buy(self, strategy_cfg, symbol: str, amount_usd: float,
                  fee_pct: float, real_usdt_available: float) -> tuple[bool, str | None]:
        """Valida una compra. Devuelve (ok, motivo_de_rechazo)."""
        sid = strategy_cfg.strategy_id
        if self.blocked:
            return False, "balance_mismatch"
        if self.ledger.position(sid, symbol) is not None:
            return False, "position_open"
        max_daily = strategy_cfg.portfolio.get("max_daily_trades", 6)
        if self.ledger.buys_today(sid) >= max_daily:
            return False, "daily_limit"
        if amount_usd < MIN_ORDER_USD:
            return False, "min_order"
        cost = amount_usd * (1 + fee_pct)
        if cost > self.ledger.cash(sid):
            return False, "no_capital"
        if cost > real_usdt_available:
            return False, "insufficient_real_balance"
        return True, None

    def check_sell(self, strategy_cfg, symbol: str) -> tuple[bool, str | None]:
        if self.blocked:
            return False, "balance_mismatch"
        if self.ledger.position(strategy_cfg.strategy_id, symbol) is None:
            return False, "no_position"
        return True, None
