"""Trap Order parameter calculator.

Computes entry price, stop loss, take profit, and position sizing
for the "Swing Sniper" Trap Order execution strategy.

Architecture ref: ARCHITECTURE.md Section 8.E.
Roadmap ref: Step 2A.4.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.shared.logger import get_logger

logger = get_logger(__name__)

# Trap Order entry offset: High + (0.02 × ATR)
ENTRY_ATR_FACTOR = 0.02

# Trap Order limit offset: entry + (0.05 × ATR)
LIMIT_ATR_FACTOR = 0.05

# Stop loss: 2 × ATR below entry
STOP_LOSS_ATR_MULTIPLE = 2.0

# Take-profit ADX scaling bounds
TP_BASE = 2.0
TP_ADX_DIVISOR = 30.0
TP_MIN_MULTIPLE = 2.5
TP_MAX_MULTIPLE = 4.5

# Maximum position as fraction of portfolio (concentration cap)
DEFAULT_MAX_POSITION_PCT = 0.15


@dataclass(frozen=True)
class TrapOrderParams:
    """Calculated Trap Order parameters for a signal.

    Attributes:
        entry_price: Buy Stop price (Signal Candle High + 0.02 × ATR).
        entry_limit: Limit price (entry + 0.05 × ATR).
        stop_loss: Stop loss price (entry − 2 × ATR).
        take_profit: Take profit price (ADX-scaled ATR).
        tp_multiplier: ATR multiplier used for TP (2.5–4.5).
        position_size: Number of units (shares/lots).
        risk_amount: Dollar/euro risk per trade.
        risk_pct: Risk as fraction of portfolio (e.g. 0.01).
        reward_risk_ratio: TP distance / SL distance.
    """

    entry_price: float
    entry_limit: float
    stop_loss: float
    take_profit: float
    tp_multiplier: float
    position_size: float
    risk_amount: float
    risk_pct: float
    reward_risk_ratio: float


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value between lo and hi (inclusive).

    Args:
        value: Value to clamp.
        lo: Minimum bound.
        hi: Maximum bound.

    Returns:
        Clamped value.
    """
    return max(lo, min(hi, value))


class TrapOrderCalculator:
    """Calculates Trap Order parameters for signal cards.

    Pure calculation — no I/O, no state. All inputs are passed
    explicitly so the caller controls where data comes from.
    """

    def calculate(
        self,
        signal_candle_high: float,
        atr_14: float,
        adx_14: float,
        portfolio_equity: float,
        risk_per_trade_pct: float,
        max_position_pct: float = DEFAULT_MAX_POSITION_PCT,
    ) -> TrapOrderParams:
        """Calculate Trap Order parameters.

        Args:
            signal_candle_high: High price of the signal candle.
            atr_14: ATR(14) value for the signal candle.
            adx_14: ADX(14) value for the signal candle.
            portfolio_equity: Total portfolio equity in base currency.
            risk_per_trade_pct: Risk per trade as fraction (e.g. 0.02 = 2%).
            max_position_pct: Max position as fraction of portfolio (default 0.15).

        Returns:
            TrapOrderParams with all calculated values.

        Raises:
            ValueError: If ATR <= 0 or portfolio_equity <= 0.
        """
        if atr_14 <= 0:
            raise ValueError(f"ATR must be > 0, got {atr_14}")
        if portfolio_equity <= 0:
            raise ValueError(
                f"Portfolio equity must be > 0, got {portfolio_equity}"
            )

        # Entry: Buy Stop at High + (0.02 × ATR)
        entry_price = signal_candle_high + ENTRY_ATR_FACTOR * atr_14

        # Limit: entry + (0.05 × ATR)
        entry_limit = entry_price + LIMIT_ATR_FACTOR * atr_14

        # Stop loss: entry − 2 × ATR
        stop_loss = entry_price - STOP_LOSS_ATR_MULTIPLE * atr_14

        # Take-profit: ADX-scaled ATR multiple, clamped [2.5, 4.5]
        adx_clamped = max(adx_14, 0.0)
        tp_multiplier = _clamp(
            TP_BASE + adx_clamped / TP_ADX_DIVISOR,
            TP_MIN_MULTIPLE,
            TP_MAX_MULTIPLE,
        )
        take_profit = entry_price + tp_multiplier * atr_14

        # Position sizing — dual constraint
        risk_per_unit = STOP_LOSS_ATR_MULTIPLE * atr_14  # 2 × ATR
        risk_budget_size = (portfolio_equity * risk_per_trade_pct) / risk_per_unit
        cap_size = (portfolio_equity * max_position_pct) / entry_price
        position_size = min(risk_budget_size, cap_size)

        # Risk amount
        risk_amount = position_size * risk_per_unit

        # Reward:risk ratio
        tp_distance = take_profit - entry_price
        sl_distance = entry_price - stop_loss
        reward_risk_ratio = tp_distance / sl_distance

        logger.info(
            f"Trap Order: entry={entry_price:.2f}, SL={stop_loss:.2f}, "
            f"TP={take_profit:.2f} ({tp_multiplier:.1f}×ATR), "
            f"size={position_size:.2f}, R:R={reward_risk_ratio:.1f}"
        )

        return TrapOrderParams(
            entry_price=entry_price,
            entry_limit=entry_limit,
            stop_loss=stop_loss,
            take_profit=take_profit,
            tp_multiplier=tp_multiplier,
            position_size=position_size,
            risk_amount=risk_amount,
            risk_pct=risk_per_trade_pct,
            reward_risk_ratio=reward_risk_ratio,
        )
