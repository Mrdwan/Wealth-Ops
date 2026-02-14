"""Tests for SignalCard and SignalCardFormatter."""

import pytest

from src.modules.signals.signal_card import (
    SignalCard,
    SignalCardFormatter,
    _format_component_name,
    _tax_label_for_broker,
    _ttl_label_for_asset_class,
)


@pytest.fixture
def sample_card() -> SignalCard:
    """Create a sample SignalCard for testing."""
    return SignalCard(
        ticker="XAU/USD",
        direction="LONG",
        signal_classification="BUY",
        composite_score=1.9,
        component_scores={
            "momentum": 1.8,
            "trend": 0.9,
            "rsi": 0.5,
            "volatility": -0.3,
            "sr": 0.2,
        },
        component_weights={
            "momentum": 0.4444,
            "trend": 0.2222,
            "rsi": 0.1667,
            "volatility": 0.1111,
            "sr": 0.0556,
        },
        entry_price=2352.00,
        entry_limit=2354.00,
        stop_loss=2310.00,
        take_profit=2410.00,
        position_size=0.02,
        risk_amount=30.0,
        risk_pct=0.01,
        reward_risk_ratio=1.38,
        broker="IG",
        tax_label="TAX FREE",
        ttl_label="1 session",
        adx_value=28.0,
        rsi_value=58.0,
        ema_fan_aligned=True,
    )


@pytest.fixture
def sample_card_ibkr() -> SignalCard:
    """Create a sample IBKR equity SignalCard."""
    return SignalCard(
        ticker="AAPL",
        direction="LONG",
        signal_classification="STRONG_BUY",
        composite_score=2.3,
        component_scores={
            "momentum": 2.1,
            "trend": 1.2,
            "rsi": 0.7,
            "volume": 0.4,
            "volatility": -0.2,
            "sr": 0.1,
        },
        component_weights={
            "momentum": 0.40,
            "trend": 0.20,
            "rsi": 0.15,
            "volume": 0.10,
            "volatility": 0.10,
            "sr": 0.05,
        },
        entry_price=185.50,
        entry_limit=185.80,
        stop_loss=175.50,
        take_profit=200.50,
        position_size=5.0,
        risk_amount=50.0,
        risk_pct=0.015,
        reward_risk_ratio=1.5,
        broker="IBKR",
        tax_label="33% CGT",
        ttl_label="1 session",
        adx_value=35.0,
        rsi_value=52.0,
        ema_fan_aligned=True,
    )


class TestSignalCardDataclass:
    """Tests for SignalCard dataclass."""

    def test_creation(self, sample_card: SignalCard) -> None:
        """Test SignalCard creates with all fields."""
        assert sample_card.ticker == "XAU/USD"
        assert sample_card.direction == "LONG"
        assert sample_card.composite_score == 1.9
        assert sample_card.broker == "IG"
        assert sample_card.tax_label == "TAX FREE"

    def test_frozen(self, sample_card: SignalCard) -> None:
        """Test SignalCard is immutable."""
        with pytest.raises(AttributeError):
            sample_card.ticker = "AAPL"  # type: ignore[misc]

    def test_top_contributors_default_3(self, sample_card: SignalCard) -> None:
        """Top 3 contributors by absolute z-score."""
        top = sample_card.top_contributors()
        assert len(top) == 3
        # momentum=1.8, trend=0.9, rsi=0.5 → sorted by abs
        assert top[0] == ("momentum", 1.8)
        assert top[1] == ("trend", 0.9)
        assert top[2] == ("rsi", 0.5)

    def test_top_contributors_custom_n(self, sample_card: SignalCard) -> None:
        """Request top 2 contributors."""
        top = sample_card.top_contributors(n=2)
        assert len(top) == 2

    def test_top_contributors_with_volume(
        self, sample_card_ibkr: SignalCard
    ) -> None:
        """Top contributors include volume for EQUITY cards."""
        top = sample_card_ibkr.top_contributors(3)
        names = [name for name, _ in top]
        # momentum=2.1, trend=1.2, rsi=0.7 are the top 3
        assert "momentum" in names

    def test_top_contributors_negative_sorted_by_abs(self) -> None:
        """Negative z-scores sorted correctly by absolute value."""
        card = SignalCard(
            ticker="TEST",
            direction="LONG",
            signal_classification="BUY",
            composite_score=1.0,
            component_scores={
                "momentum": -2.0,
                "trend": 1.5,
                "rsi": 0.3,
            },
            component_weights={"momentum": 0.5, "trend": 0.3, "rsi": 0.2},
            entry_price=100.0,
            entry_limit=101.0,
            stop_loss=95.0,
            take_profit=110.0,
            position_size=1.0,
            risk_amount=5.0,
            risk_pct=0.01,
            reward_risk_ratio=2.0,
            broker="PAPER",
            tax_label="PAPER",
            ttl_label="1 session",
            adx_value=25.0,
            rsi_value=50.0,
            ema_fan_aligned=False,
        )
        top = card.top_contributors(3)
        # -2.0 abs=2.0 > 1.5 abs=1.5 > 0.3 abs=0.3
        assert top[0] == ("momentum", -2.0)
        assert top[1] == ("trend", 1.5)


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_tax_label_ig(self) -> None:
        """IG → TAX FREE."""
        assert _tax_label_for_broker("IG") == "TAX FREE"

    def test_tax_label_ibkr(self) -> None:
        """IBKR → 33% CGT."""
        assert _tax_label_for_broker("IBKR") == "33% CGT"

    def test_tax_label_paper(self) -> None:
        """PAPER → PAPER."""
        assert _tax_label_for_broker("PAPER") == "PAPER"

    def test_tax_label_unknown(self) -> None:
        """Unknown broker returns the broker string."""
        assert _tax_label_for_broker("UNKNOWN_BROKER") == "UNKNOWN_BROKER"

    def test_ttl_equity(self) -> None:
        """EQUITY → 1 session."""
        assert _ttl_label_for_asset_class("EQUITY") == "1 session"

    def test_ttl_commodity(self) -> None:
        """COMMODITY → 24 hours."""
        assert _ttl_label_for_asset_class("COMMODITY") == "24 hours"

    def test_ttl_forex(self) -> None:
        """FOREX → 24 hours."""
        assert _ttl_label_for_asset_class("FOREX") == "24 hours"

    def test_ttl_unknown_defaults_to_session(self) -> None:
        """Unknown asset class defaults to 1 session."""
        assert _ttl_label_for_asset_class("INDEX") == "1 session"

    def test_format_component_name_known(self) -> None:
        """Known component names map to display labels."""
        assert _format_component_name("momentum") == "Momentum"
        assert _format_component_name("sr") == "Support/Resistance"

    def test_format_component_name_unknown(self) -> None:
        """Unknown component names get title-cased."""
        assert _format_component_name("new_component") == "New_Component"


class TestSignalCardFormatter:
    """Tests for SignalCardFormatter."""

    def test_format_contains_all_elements(
        self, sample_card: SignalCard
    ) -> None:
        """Formatted card contains all required information."""
        formatter = SignalCardFormatter()
        text = formatter.format(sample_card)

        # Signal header
        assert "WEALTH-OPS SIGNAL" in text
        assert "LONG" in text
        assert "XAU/USD" in text

        # Confidence
        assert "1.9σ" in text
        assert "BUY" in text

        # Trap Order
        assert "$2,352.00" in text
        assert "$2,354.00" in text

        # Stop loss
        assert "$2,310.00" in text

        # Take profit
        assert "$2,410.00" in text
        assert "Close 50%" in text

        # Chandelier reference
        assert "Chandelier" in text

        # Size and risk
        assert "0.02 units" in text
        assert "€30 risk" in text
        assert "1.0%" in text

        # R:R
        assert "1:1.4" in text

        # Broker
        assert "IG" in text
        assert "TAX FREE" in text

        # Reasoning (top contributors)
        assert "Momentum" in text

        # EMA fan
        assert "aligned (8 > 20 > 50)" in text

        # RSI and ADX
        assert "RSI: 58" in text
        assert "ADX: 28" in text

        # TTL
        assert "1 session" in text

        # Commands
        assert "/executed" in text
        assert "/skip" in text
        assert "/details" in text

    def test_format_strong_buy_emoji(
        self, sample_card_ibkr: SignalCard
    ) -> None:
        """STRONG_BUY uses green circle emoji."""
        formatter = SignalCardFormatter()
        text = formatter.format(sample_card_ibkr)
        assert "🟢" in text

    def test_format_buy_emoji(self, sample_card: SignalCard) -> None:
        """BUY uses yellow circle emoji."""
        formatter = SignalCardFormatter()
        text = formatter.format(sample_card)
        assert "🟡" in text

    def test_format_no_volume_components(
        self, sample_card: SignalCard
    ) -> None:
        """Card without volume component shows 5 components."""
        formatter = SignalCardFormatter()
        text = formatter.format(sample_card)
        # Volume should not appear since sample_card has no volume component
        assert "Volume:" not in text

    def test_format_with_volume_component(
        self, sample_card_ibkr: SignalCard
    ) -> None:
        """IBKR card may include volume in reasoning if it's a top contributor."""
        formatter = SignalCardFormatter()
        text = formatter.format(sample_card_ibkr)
        # Volume is not top 3 for this card (momentum=2.1, trend=1.2, rsi=0.7)
        assert "IBKR" in text
        assert "33% CGT" in text

    def test_format_cgt_broker(self, sample_card_ibkr: SignalCard) -> None:
        """IBKR card shows '33% CGT'."""
        formatter = SignalCardFormatter()
        text = formatter.format(sample_card_ibkr)
        assert "33% CGT" in text

    def test_format_ema_not_aligned(self) -> None:
        """EMA fan not aligned text is shown."""
        card = SignalCard(
            ticker="TEST",
            direction="LONG",
            signal_classification="NEUTRAL",
            composite_score=0.5,
            component_scores={"momentum": 0.3, "trend": 0.2, "rsi": 0.1},
            component_weights={"momentum": 0.5, "trend": 0.3, "rsi": 0.2},
            entry_price=100.0,
            entry_limit=101.0,
            stop_loss=95.0,
            take_profit=110.0,
            position_size=1.0,
            risk_amount=5.0,
            risk_pct=0.01,
            reward_risk_ratio=2.0,
            broker="PAPER",
            tax_label="PAPER",
            ttl_label="1 session",
            adx_value=15.0,
            rsi_value=45.0,
            ema_fan_aligned=False,
        )
        formatter = SignalCardFormatter()
        text = formatter.format(card)
        assert "not aligned" in text

    def test_signal_emoji_sell(self) -> None:
        """SELL and STRONG_SELL use red emoji."""
        formatter = SignalCardFormatter()
        assert formatter._signal_emoji("SELL") == "🔴"
        assert formatter._signal_emoji("STRONG_SELL") == "🔴"

    def test_signal_emoji_neutral(self) -> None:
        """NEUTRAL uses white emoji."""
        formatter = SignalCardFormatter()
        assert formatter._signal_emoji("NEUTRAL") == "⚪"

    def test_signal_emoji_unknown(self) -> None:
        """Unknown classification defaults to white emoji."""
        formatter = SignalCardFormatter()
        assert formatter._signal_emoji("INVALID") == "⚪"

    def test_format_reasoning_lines(self, sample_card: SignalCard) -> None:
        """Reasoning lines show component name, z-score, and weight."""
        formatter = SignalCardFormatter()
        lines = formatter._format_reasoning(sample_card)
        assert len(lines) == 3
        # First line should be momentum (highest abs z-score)
        assert "Momentum" in lines[0]
        assert "+1.80" in lines[0]
        assert "44%" in lines[0]
