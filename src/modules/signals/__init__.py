"""Signal generation modules.

Consumes features from the Feature Engine and produces trade signals.
"""

from src.modules.signals.market_context import MarketContext, MarketDataLoader
from src.modules.signals.signal_card import (
    SignalCard,
    SignalCardFormatter,
)
from src.modules.signals.staleness_guard import (
    StalenessGuard,
    StalenessResult,
    SourceStaleness,
)
from src.modules.signals.trap_order import TrapOrderCalculator, TrapOrderParams

__all__ = [
    "MarketContext",
    "MarketDataLoader",
    "SignalCard",
    "SignalCardFormatter",
    "SourceStaleness",
    "StalenessGuard",
    "StalenessResult",
    "TrapOrderCalculator",
    "TrapOrderParams",
]
