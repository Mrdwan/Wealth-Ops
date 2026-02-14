"""Signal generation modules.

Consumes features from the Feature Engine and produces trade signals.
"""

from src.modules.signals.signal_card import (
    SignalCard,
    SignalCardFormatter,
)
from src.modules.signals.trap_order import TrapOrderCalculator, TrapOrderParams

__all__ = [
    "SignalCard",
    "SignalCardFormatter",
    "TrapOrderCalculator",
    "TrapOrderParams",
]
