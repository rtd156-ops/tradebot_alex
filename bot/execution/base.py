"""Interfaz común para brokers (paper y live)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float


class Broker(ABC):
    @abstractmethod
    def buy(self, symbol: str, usd_amount: float, price: float) -> bool: ...

    @abstractmethod
    def sell(self, symbol: str, price: float) -> bool: ...

    @abstractmethod
    def get_position(self, symbol: str) -> Position | None: ...

    @abstractmethod
    def get_cash(self) -> float: ...

    @abstractmethod
    def portfolio_value(self, prices: dict[str, float]) -> float: ...
