"""Tests for Trap Order calculator."""

import pytest

from src.modules.signals.trap_order import (
    TrapOrderCalculator,
    TrapOrderParams,
)


@pytest.fixture
def calculator() -> TrapOrderCalculator:
    """Create TrapOrderCalculator instance."""
    return TrapOrderCalculator()


class TestTrapOrderBasicCalculation:
    """Tests for basic Trap Order parameter calculations."""

    def test_basic_calculation(self, calculator: TrapOrderCalculator) -> None:
        """Test known-good inputs produce correct results."""
        # ATR=10, ADX=30, High=100, Portfolio=10000, Risk=2%
        result = calculator.calculate(
            signal_candle_high=100.0,
            atr_14=10.0,
            adx_14=30.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
        )

        assert isinstance(result, TrapOrderParams)

        # entry = 100 + 0.02 * 10 = 100.20
        assert result.entry_price == pytest.approx(100.20)

        # limit = 100.20 + 0.05 * 10 = 100.70
        assert result.entry_limit == pytest.approx(100.70)

        # SL = 100.20 - 2 * 10 = 80.20
        assert result.stop_loss == pytest.approx(80.20)

        # TP mult = clamp(2 + 30/30 = 3.0, 2.5, 4.5) = 3.0
        assert result.tp_multiplier == pytest.approx(3.0)

        # TP = 100.20 + 3.0 * 10 = 130.20
        assert result.take_profit == pytest.approx(130.20)

        # risk_size = (10000 * 0.02) / (2 * 10) = 200 / 20 = 10
        # cap_size = (10000 * 0.15) / 100.20 ≈ 14.97
        # size = min(10, 14.97) = 10
        assert result.position_size == pytest.approx(10.0)

        # risk_amount = 10 * 20 = 200
        assert result.risk_amount == pytest.approx(200.0)

        # R:R = (130.20 - 100.20) / (100.20 - 80.20) = 30 / 20 = 1.5
        assert result.reward_risk_ratio == pytest.approx(1.5)

        assert result.risk_pct == pytest.approx(0.02)

    def test_entry_price_formula(self, calculator: TrapOrderCalculator) -> None:
        """Test entry = high + 0.02 × ATR exactly."""
        result = calculator.calculate(
            signal_candle_high=200.0,
            atr_14=5.0,
            adx_14=25.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
        )
        # 200 + 0.02 * 5 = 200.10
        assert result.entry_price == pytest.approx(200.10)

    def test_stop_loss_formula(self, calculator: TrapOrderCalculator) -> None:
        """Test SL = entry − 2 × ATR."""
        result = calculator.calculate(
            signal_candle_high=50.0,
            atr_14=3.0,
            adx_14=20.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
        )
        # entry = 50 + 0.02*3 = 50.06
        # SL = 50.06 - 2*3 = 44.06
        assert result.stop_loss == pytest.approx(44.06)


class TestTakeProfitAdxScaling:
    """Tests for ADX-scaled TP multiplier clamping."""

    def test_adx_zero_gives_minimum_tp(
        self, calculator: TrapOrderCalculator
    ) -> None:
        """ADX=0 → TP mult = clamp(2+0/30=2.0, 2.5, 4.5) = 2.5."""
        result = calculator.calculate(
            signal_candle_high=100.0,
            atr_14=10.0,
            adx_14=0.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
        )
        assert result.tp_multiplier == pytest.approx(2.5)

    def test_adx_45_gives_midrange_tp(
        self, calculator: TrapOrderCalculator
    ) -> None:
        """ADX=45 → TP mult = clamp(2+45/30=3.5, 2.5, 4.5) = 3.5."""
        result = calculator.calculate(
            signal_candle_high=100.0,
            atr_14=10.0,
            adx_14=45.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
        )
        assert result.tp_multiplier == pytest.approx(3.5)

    def test_adx_75_clamped_to_max_tp(
        self, calculator: TrapOrderCalculator
    ) -> None:
        """ADX=75 → TP mult = clamp(2+75/30=4.5, 2.5, 4.5) = 4.5."""
        result = calculator.calculate(
            signal_candle_high=100.0,
            atr_14=10.0,
            adx_14=75.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
        )
        assert result.tp_multiplier == pytest.approx(4.5)

    def test_adx_100_clamped_to_max_tp(
        self, calculator: TrapOrderCalculator
    ) -> None:
        """ADX=100 → TP mult should still clamp to 4.5."""
        result = calculator.calculate(
            signal_candle_high=100.0,
            atr_14=10.0,
            adx_14=100.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
        )
        assert result.tp_multiplier == pytest.approx(4.5)

    def test_negative_adx_clamped_to_zero(
        self, calculator: TrapOrderCalculator
    ) -> None:
        """Negative ADX is clamped to 0 → TP mult = 2.5 (minimum)."""
        result = calculator.calculate(
            signal_candle_high=100.0,
            atr_14=10.0,
            adx_14=-5.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
        )
        assert result.tp_multiplier == pytest.approx(2.5)


class TestPositionSizing:
    """Tests for dual-constraint position sizing."""

    def test_risk_budget_wins(self, calculator: TrapOrderCalculator) -> None:
        """Risk budget produces smaller size than cap → risk_budget chosen."""
        # ATR=10, entry≈100.20, risk_size = (10000*0.02)/(20) = 10
        # cap_size = (10000*0.15)/100.20 ≈ 14.97
        # min(10, 14.97) → 10 (risk budget wins)
        result = calculator.calculate(
            signal_candle_high=100.0,
            atr_14=10.0,
            adx_14=30.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
        )
        assert result.position_size == pytest.approx(10.0)

    def test_cap_wins(self, calculator: TrapOrderCalculator) -> None:
        """Cap produces smaller size than risk budget → cap chosen."""
        # High risk_pct so risk_budget_size is very large
        # ATR=1, entry≈10.02
        # risk_size = (10000 * 0.10) / (2 * 1) = 500
        # cap_size = (10000 * 0.15) / 10.02 ≈ 14.97
        # min(500, 14.97) → 14.97 (cap wins)
        result = calculator.calculate(
            signal_candle_high=10.0,
            atr_14=1.0,
            adx_14=30.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.10,
        )
        cap_size = (10000 * 0.15) / result.entry_price
        assert result.position_size == pytest.approx(cap_size)

    def test_custom_max_position_pct(
        self, calculator: TrapOrderCalculator
    ) -> None:
        """Custom max_position_pct is respected."""
        result = calculator.calculate(
            signal_candle_high=100.0,
            atr_14=10.0,
            adx_14=30.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
            max_position_pct=0.05,
        )
        # cap_size = (10000*0.05)/100.20 ≈ 4.99
        # risk_size = 10
        # min(10, 4.99) → cap wins
        cap_size = (10000 * 0.05) / result.entry_price
        assert result.position_size == pytest.approx(cap_size)


class TestRewardRiskRatio:
    """Tests for R:R calculation."""

    def test_reward_risk_ratio(self, calculator: TrapOrderCalculator) -> None:
        """R:R = (TP - entry) / (entry - SL)."""
        result = calculator.calculate(
            signal_candle_high=100.0,
            atr_14=10.0,
            adx_14=30.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
        )
        expected_rr = (result.take_profit - result.entry_price) / (
            result.entry_price - result.stop_loss
        )
        assert result.reward_risk_ratio == pytest.approx(expected_rr)

    def test_rr_equals_tp_multiplier_over_sl_multiplier(
        self, calculator: TrapOrderCalculator
    ) -> None:
        """R:R should equal tp_multiplier / SL_multiplier (= 2)."""
        result = calculator.calculate(
            signal_candle_high=100.0,
            atr_14=10.0,
            adx_14=30.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
        )
        # TP mult = 3.0, SL mult = 2.0 → R:R = 3.0/2.0 = 1.5
        assert result.reward_risk_ratio == pytest.approx(
            result.tp_multiplier / 2.0
        )


class TestTrapOrderErrors:
    """Tests for error cases."""

    def test_atr_zero_raises_value_error(
        self, calculator: TrapOrderCalculator
    ) -> None:
        """ATR = 0 raises ValueError."""
        with pytest.raises(ValueError, match="ATR must be > 0"):
            calculator.calculate(
                signal_candle_high=100.0,
                atr_14=0.0,
                adx_14=30.0,
                portfolio_equity=10000.0,
                risk_per_trade_pct=0.02,
            )

    def test_atr_negative_raises_value_error(
        self, calculator: TrapOrderCalculator
    ) -> None:
        """Negative ATR raises ValueError."""
        with pytest.raises(ValueError, match="ATR must be > 0"):
            calculator.calculate(
                signal_candle_high=100.0,
                atr_14=-1.0,
                adx_14=30.0,
                portfolio_equity=10000.0,
                risk_per_trade_pct=0.02,
            )

    def test_portfolio_zero_raises_value_error(
        self, calculator: TrapOrderCalculator
    ) -> None:
        """Portfolio = 0 raises ValueError."""
        with pytest.raises(ValueError, match="Portfolio equity must be > 0"):
            calculator.calculate(
                signal_candle_high=100.0,
                atr_14=10.0,
                adx_14=30.0,
                portfolio_equity=0.0,
                risk_per_trade_pct=0.02,
            )

    def test_portfolio_negative_raises_value_error(
        self, calculator: TrapOrderCalculator
    ) -> None:
        """Negative portfolio raises ValueError."""
        with pytest.raises(ValueError, match="Portfolio equity must be > 0"):
            calculator.calculate(
                signal_candle_high=100.0,
                atr_14=10.0,
                adx_14=30.0,
                portfolio_equity=-1000.0,
                risk_per_trade_pct=0.02,
            )


class TestTrapOrderParamsDataclass:
    """Tests for the TrapOrderParams frozen dataclass."""

    def test_params_are_frozen(self, calculator: TrapOrderCalculator) -> None:
        """TrapOrderParams should be immutable."""
        result = calculator.calculate(
            signal_candle_high=100.0,
            atr_14=10.0,
            adx_14=30.0,
            portfolio_equity=10000.0,
            risk_per_trade_pct=0.02,
        )
        with pytest.raises(AttributeError):
            result.entry_price = 999.0  # type: ignore[misc]
