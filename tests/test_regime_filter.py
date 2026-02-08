"""Tests for Regime Filter module."""

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.modules.regime.filter import MarketStatus, RegimeFilter
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
def bull_market_df() -> pd.DataFrame:
    """DataFrame where current close > 200-day SMA (BULL)."""
    # 250 days of data with upward trend
    dates = [date(2024, 1, 1) + pd.Timedelta(days=i) for i in range(250)]
    closes = [100 + i * 0.5 for i in range(250)]  # Upward trend

    df = pd.DataFrame({"close": closes}, index=dates)
    df.index.name = "date"
    return df


@pytest.fixture
def bear_market_df() -> pd.DataFrame:
    """DataFrame where current close < 200-day SMA (BEAR)."""
    # 250 days of data with downward trend at end
    dates = [date(2024, 1, 1) + pd.Timedelta(days=i) for i in range(250)]
    closes = [200 - i * 0.3 for i in range(250)]  # Downward trend

    df = pd.DataFrame({"close": closes}, index=dates)
    df.index.name = "date"
    return df


class TestRegimeFilter:
    """Tests for RegimeFilter."""

    def test_bull_market_detected(
        self,
        config: Config,
        bull_market_df: pd.DataFrame,
    ) -> None:
        """Test BULL status when close > SMA200."""
        mock_provider = MagicMock()
        mock_provider.get_daily_candles.return_value = bull_market_df

        mock_dynamodb = MagicMock()
        mock_dynamodb.put_item.return_value = {}

        filter = RegimeFilter(
            config=config,
            provider=mock_provider,
            dynamodb_client=mock_dynamodb,
        )

        status = filter.evaluate()

        assert status == MarketStatus.BULL
        mock_dynamodb.put_item.assert_called_once()

    def test_bear_market_detected(
        self,
        config: Config,
        bear_market_df: pd.DataFrame,
    ) -> None:
        """Test BEAR status when close < SMA200."""
        mock_provider = MagicMock()
        mock_provider.get_daily_candles.return_value = bear_market_df

        mock_dynamodb = MagicMock()
        mock_dynamodb.put_item.return_value = {}

        filter = RegimeFilter(
            config=config,
            provider=mock_provider,
            dynamodb_client=mock_dynamodb,
        )

        status = filter.evaluate()

        assert status == MarketStatus.BEAR

    def test_unknown_on_insufficient_data(self, config: Config) -> None:
        """Test UNKNOWN when not enough data for 200-day MA."""
        # Only 50 days of data
        dates = [date(2024, 1, 1) + pd.Timedelta(days=i) for i in range(50)]
        closes = [100 + i for i in range(50)]
        df = pd.DataFrame({"close": closes}, index=dates)
        df.index.name = "date"

        mock_provider = MagicMock()
        mock_provider.get_daily_candles.return_value = df

        mock_dynamodb = MagicMock()

        filter = RegimeFilter(
            config=config,
            provider=mock_provider,
            dynamodb_client=mock_dynamodb,
        )

        status = filter.evaluate()

        assert status == MarketStatus.UNKNOWN

    def test_get_current_status_from_dynamodb(self, config: Config) -> None:
        """Test reading current status from DynamoDB."""
        mock_provider = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.get_item.return_value = {
            "Item": {
                "key": {"S": "market_status"},
                "value": {"S": "BULL"},
            }
        }

        filter = RegimeFilter(
            config=config,
            provider=mock_provider,
            dynamodb_client=mock_dynamodb,
        )

        status = filter.get_current_status()

        assert status == MarketStatus.BULL
