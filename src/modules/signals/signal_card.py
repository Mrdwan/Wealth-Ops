"""Signal Card — data model and Telegram formatter.

Defines the SignalCard dataclass and SignalCardFormatter for composing
actionable Telegram signal cards with entry zones, stops, targets,
position sizing, and composite score breakdowns.

Architecture ref: ARCHITECTURE.md Section 12.1.
Roadmap ref: Step 2A.4.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalCard:
    """All data needed to render a signal card message.

    Attributes:
        ticker: Asset symbol (e.g. "XAU/USD", "AAPL").
        direction: Trade direction ("LONG").
        signal_classification: From CompositeResult (e.g. "STRONG_BUY").
        composite_score: Final weighted z-score.
        component_scores: Per-component z-scores.
        component_weights: Weights applied to each component.
        entry_price: Trap Order entry price.
        entry_limit: Trap Order limit price.
        stop_loss: Stop loss price.
        take_profit: Take profit price (close 50%).
        position_size: Number of units.
        risk_amount: Dollar/euro amount at risk.
        risk_pct: Risk as fraction of portfolio (e.g. 0.01).
        reward_risk_ratio: TP distance / SL distance.
        broker: Execution broker (IG, IBKR, PAPER).
        tax_label: Tax description ("TAX FREE" or "33% CGT").
        ttl_label: Order validity ("1 session" or "24 hours").
        adx_value: ADX(14) value for the signal candle.
        rsi_value: RSI(14) value for the signal candle.
        ema_fan_aligned: Whether EMA 8 > 20 > 50.
    """

    ticker: str
    direction: str
    signal_classification: str
    composite_score: float
    component_scores: dict[str, float]
    component_weights: dict[str, float]
    entry_price: float
    entry_limit: float
    stop_loss: float
    take_profit: float
    position_size: float
    risk_amount: float
    risk_pct: float
    reward_risk_ratio: float
    broker: str
    tax_label: str
    ttl_label: str
    adx_value: float
    rsi_value: float
    ema_fan_aligned: bool

    def top_contributors(self, n: int = 3) -> list[tuple[str, float]]:
        """Return top N components by absolute z-score.

        Args:
            n: Number of top contributors to return.

        Returns:
            List of (component_name, z_score) tuples, descending by abs value.
        """
        sorted_components = sorted(
            self.component_scores.items(),
            key=lambda item: abs(item[1]),
            reverse=True,
        )
        return sorted_components[:n]


def _tax_label_for_broker(broker: str) -> str:
    """Derive tax label from broker name.

    Args:
        broker: Broker identifier (IG, IBKR, PAPER).

    Returns:
        Human-readable tax label.
    """
    labels: dict[str, str] = {
        "IG": "TAX FREE",
        "IBKR": "33% CGT",
        "PAPER": "PAPER",
    }
    return labels.get(broker, broker)


def _ttl_label_for_asset_class(asset_class: str) -> str:
    """Derive TTL label from asset class.

    Args:
        asset_class: Asset class (EQUITY, COMMODITY, FOREX).

    Returns:
        Human-readable TTL label.
    """
    if asset_class in ("COMMODITY", "FOREX"):
        return "24 hours"
    return "1 session"


def _format_component_name(name: str) -> str:
    """Format a component key for display.

    Args:
        name: Internal component key (e.g. "momentum", "sr").

    Returns:
        Human-readable label.
    """
    display_names: dict[str, str] = {
        "momentum": "Momentum",
        "trend": "Trend",
        "rsi": "RSI",
        "volume": "Volume",
        "volatility": "Volatility",
        "sr": "Support/Resistance",
    }
    return display_names.get(name, name.title())


class SignalCardFormatter:
    """Formats a SignalCard into a Telegram message string.

    Produces the signal card format defined in ARCHITECTURE.md Section 12.1.
    Output uses plain text (no Markdown) for maximum Telegram compatibility.
    """

    def format(self, card: SignalCard) -> str:
        """Format a SignalCard into a Telegram-ready message.

        Args:
            card: Populated SignalCard dataclass.

        Returns:
            Formatted signal card string.
        """
        signal_emoji = self._signal_emoji(card.signal_classification)
        sl_pct = ((card.stop_loss - card.entry_price) / card.entry_price) * 100
        tp_pct = ((card.take_profit - card.entry_price) / card.entry_price) * 100
        risk_pct_display = card.risk_pct * 100

        # Top contributors reasoning
        reasoning_lines = self._format_reasoning(card)

        # EMA fan status
        ema_status = "aligned (8 > 20 > 50)" if card.ema_fan_aligned else "not aligned"

        lines = [
            f"{signal_emoji} WEALTH-OPS SIGNAL — {card.direction} {card.ticker}",
            "",
            f"📊 Confidence: Momentum {card.composite_score:.1f}σ ({card.signal_classification})",
            f"🎯 Trap Order: Stop at ${card.entry_price:,.2f} | Limit at ${card.entry_limit:,.2f}",
            f"🛑 Stop Loss: ${card.stop_loss:,.2f} ({sl_pct:+.1f}%)",
            f"✅ TP: ${card.take_profit:,.2f} ({tp_pct:+.1f}%) — Close 50%",
            f"📐 Trail: Chandelier at HH - (2 × ATR)",
            "",
            f"💰 Size: {card.position_size:.2f} units (€{card.risk_amount:,.0f} risk = {risk_pct_display:.1f}%)",
            f"⚖️ R:R: 1:{card.reward_risk_ratio:.1f}",
            f"🏷️ Broker: {card.broker} ({card.tax_label})",
            "",
            "📈 Reasoning:",
        ]

        for line in reasoning_lines:
            lines.append(f"  • {line}")

        lines.append(f"  • EMA fan {ema_status}")
        lines.append(f"  • RSI: {card.rsi_value:.0f}")
        lines.append(f"  • ADX: {card.adx_value:.0f}")
        lines.append("")
        lines.append(f"⏰ Trap Order valid: {card.ttl_label}")
        lines.append("/executed  /skip  /details")

        return "\n".join(lines)

    def _signal_emoji(self, classification: str) -> str:
        """Map signal classification to emoji.

        Args:
            classification: Signal classification string.

        Returns:
            Emoji string.
        """
        emojis: dict[str, str] = {
            "STRONG_BUY": "🟢",
            "BUY": "🟡",
            "NEUTRAL": "⚪",
            "SELL": "🔴",
            "STRONG_SELL": "🔴",
        }
        return emojis.get(classification, "⚪")

    def _format_reasoning(self, card: SignalCard) -> list[str]:
        """Build reasoning lines from top component contributors.

        Args:
            card: Signal card with component scores.

        Returns:
            List of human-readable reasoning strings.
        """
        lines: list[str] = []
        for name, z_score in card.top_contributors(3):
            display = _format_component_name(name)
            weight = card.component_weights.get(name, 0.0)
            weight_pct = weight * 100
            lines.append(f"{display}: z={z_score:+.2f} (weight: {weight_pct:.0f}%)")
        return lines
