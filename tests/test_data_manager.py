"""Tests for DataManager orchestrator."""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.modules.data.manager import DataManager, FetchMode
from src.modules.data.protocols import ProviderError
from src.shared.config import Config


@pytest.fixture
def config() -> Config:
    """Create test configuration."""
    return Config(
        aws_region="us-east-1",
        s3_bucket="test-bucket",
        config_table="test-config",
        ledger_table="test-ledger",
        portfolio_table="test-portfolio",
        system_table="test-system",
        tiingo_api_key="test-key",
        telegram_bot_token="",
        telegram_chat_id="",
        environment="test",
    )


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Sample DataFrame for testing."""
    data = {
        "open": [150.0, 154.0],
        "high": [155.0, 158.0],
        "low": [149.0, 153.0],
        "close": [154.0, 157.0],
        "volume": [1000000, 1100000],
        "adjusted_close": [154.0, 157.0],
    }
    index = [date(2024, 1, 2), date(2024, 1, 3)]
    df = pd.DataFrame(data, index=index)
    df.index.name = "date"
    return df


class TestFetchModeLogic:
    """Tests for fetch mode determination."""

    def test_bootstrap_mode_when_no_last_updated(self, config: Config) -> None:
        """Test bootstrap mode when ticker has no history."""
        mock_primary = MagicMock()
        mock_fallback = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.get_item.return_value = {}

        manager = DataManager(
            config=config,
            primary_provider=mock_primary,
            fallback_provider=mock_fallback,
            dynamodb_client=mock_dynamodb,
            s3_client=MagicMock(),
        )

        mode, start, end = manager._determine_fetch_params(
            last_updated=None,
            today=date(2024, 1, 5),
            max_history_years=50,
        )

        assert mode == FetchMode.BOOTSTRAP
        # Start should be ~50 years ago
        assert start < date(1980, 1, 1)

    def test_daily_drip_mode_when_current(self, config: Config) -> None:
        """Test daily drip when data is current."""
        mock_primary = MagicMock()
        mock_fallback = MagicMock()

        manager = DataManager(
            config=config,
            primary_provider=mock_primary,
            fallback_provider=mock_fallback,
            dynamodb_client=MagicMock(),
            s3_client=MagicMock(),
        )

        yesterday = date.today() - timedelta(days=1)
        mode, _, _ = manager._determine_fetch_params(
            last_updated=yesterday,
            today=date.today(),
            max_history_years=50,
        )

        assert mode == FetchMode.DAILY_DRIP

    def test_gap_fill_mode_when_missing_days(self, config: Config) -> None:
        """Test gap fill when multiple days missing."""
        mock_primary = MagicMock()
        mock_fallback = MagicMock()

        manager = DataManager(
            config=config,
            primary_provider=mock_primary,
            fallback_provider=mock_fallback,
            dynamodb_client=MagicMock(),
            s3_client=MagicMock(),
        )

        five_days_ago = date.today() - timedelta(days=5)
        mode, start, end = manager._determine_fetch_params(
            last_updated=five_days_ago,
            today=date.today(),
            max_history_years=50,
        )

        assert mode == FetchMode.GAP_FILL
        assert start == five_days_ago + timedelta(days=1)


class TestProviderFailover:
    """Tests for provider failover logic."""

    def test_uses_primary_when_successful(
        self,
        config: Config,
        sample_df: pd.DataFrame,
    ) -> None:
        """Test primary provider is used when it succeeds."""
        mock_primary = MagicMock()
        mock_primary.get_daily_candles.return_value = sample_df

        mock_fallback = MagicMock()

        manager = DataManager(
            config=config,
            primary_provider=mock_primary,
            fallback_provider=mock_fallback,
            dynamodb_client=MagicMock(),
            s3_client=MagicMock(),
        )

        result = manager._fetch_with_failover("AAPL", date(2024, 1, 2), date(2024, 1, 3))

        mock_primary.get_daily_candles.assert_called_once()
        mock_fallback.get_daily_candles.assert_not_called()
        assert len(result) == 2

    def test_falls_back_when_primary_fails(
        self,
        config: Config,
        sample_df: pd.DataFrame,
    ) -> None:
        """Test fallback is used when primary fails."""
        mock_primary = MagicMock()
        mock_primary.get_daily_candles.side_effect = ProviderError("Tiingo", "AAPL", "API Error")

        mock_fallback = MagicMock()
        mock_fallback.get_daily_candles.return_value = sample_df

        manager = DataManager(
            config=config,
            primary_provider=mock_primary,
            fallback_provider=mock_fallback,
            dynamodb_client=MagicMock(),
            s3_client=MagicMock(),
        )

        result = manager._fetch_with_failover("AAPL", date(2024, 1, 2), date(2024, 1, 3))

        mock_primary.get_daily_candles.assert_called_once()
        mock_fallback.get_daily_candles.assert_called_once()
        assert len(result) == 2

    def test_raises_when_both_fail(self, config: Config) -> None:
        """Test raises when both providers fail."""
        mock_primary = MagicMock()
        mock_primary.get_daily_candles.side_effect = ProviderError("Tiingo", "AAPL", "API Error")

        mock_fallback = MagicMock()
        mock_fallback.get_daily_candles.side_effect = ProviderError("Yahoo", "AAPL", "Rate limited")

        manager = DataManager(
            config=config,
            primary_provider=mock_primary,
            fallback_provider=mock_fallback,
            dynamodb_client=MagicMock(),
            s3_client=MagicMock(),
        )

        with pytest.raises(ProviderError):
            manager._fetch_with_failover("AAPL", date(2024, 1, 2), date(2024, 1, 3))
