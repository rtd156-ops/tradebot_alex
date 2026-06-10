"""Gestión de riesgo: tamaño de posición, stop-loss, take-profit, trailing stop
y límites diarios.

El trailing stop sigue el modelo de Freqtrade: el stop fijo aplica siempre;
cuando la ganancia máxima alcanzada supera `trailing_stop_positive_offset`,
se activa un stop dinámico a `trailing_stop_positive` por debajo del pico,
que asegura ganancias dejando correr al ganador.
"""
import logging

log = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, params: dict):
        self.max_position_pct = params.get("max_position_pct", 0.15)
        self.stop_loss_pct = params.get("stop_loss_pct", 0.05)
        self.take_profit_pct = params.get("take_profit_pct", 0.10)
        self.max_daily_trades = params.get("max_daily_trades", 6)
        self.trailing_stop = params.get("trailing_stop", False)
        self.trailing_pct = params.get("trailing_stop_positive", 0.02)
        self.trailing_offset = params.get("trailing_stop_positive_offset", 0.03)

    def position_size(self, portfolio_value: float, cash: float) -> float:
        """USD a invertir en una nueva posición."""
        return min(portfolio_value * self.max_position_pct, cash * 0.95)

    def can_open(self, trades_today: int) -> bool:
        if trades_today >= self.max_daily_trades:
            log.info("Límite de %d operaciones diarias alcanzado", self.max_daily_trades)
            return False
        return True

    def check_exit(self, entry_price: float, current_price: float,
                   peak_price: float | None = None) -> str | None:
        """Devuelve 'TRAILING_STOP', 'STOP_LOSS' o 'TAKE_PROFIT' si toca cerrar."""
        if entry_price <= 0:
            return None
        if (self.trailing_stop and peak_price
                and peak_price >= entry_price * (1 + self.trailing_offset)
                and current_price <= peak_price * (1 - self.trailing_pct)):
            return "TRAILING_STOP"
        change = (current_price - entry_price) / entry_price
        if change <= -self.stop_loss_pct:
            return "STOP_LOSS"
        if change >= self.take_profit_pct:
            return "TAKE_PROFIT"
        return None
