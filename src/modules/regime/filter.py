"""Regime Filter - Market Circuit Breaker.

Determines market regime (BULL/BEAR) based on S&P 500 vs 200-day moving average.
When in BEAR mode, all buy signals are blocked.
"""

from datetime import date
from enum import Enum
from typing import Any

import boto3
import pandas as pd
from botocore.exceptions import ClientError

from src.modules.data.protocols import MarketDataProvider
from src.shared.config import Config
from src.shared.logger import get_logger

logger = get_logger(__name__)

# S&P 500 ticker symbol
SP500_TICKER = "SPY"

# Moving average period in days
MA_PERIOD = 200


class MarketStatus(Enum):
    """Market regime status."""

    BULL = "BULL"
    BEAR = "BEAR"
    UNKNOWN = "UNKNOWN"


class RegimeFilter:
    """Circuit breaker based on S&P 500 trend.

    Logic:
        - If S&P 500 close > 200-day SMA → BULL (trading allowed)
        - If S&P 500 close < 200-day SMA → BEAR (no new buys)
    """

    def __init__(
        self,
        config: Config,
        provider: MarketDataProvider,
        dynamodb_client: Any | None = None,
    ) -> None:
        """Initialize RegimeFilter.

        Args:
            config: Application configuration.
            provider: Market data provider for fetching S&P 500 data.
            dynamodb_client: Optional boto3 DynamoDB client (for testing).
        """
        self._config = config
        self._provider = provider
        self._dynamodb = dynamodb_client or boto3.client("dynamodb", region_name=config.aws_region)

    def evaluate(self) -> MarketStatus:
        """Evaluate current market regime and update DynamoDB.

        Returns:
            Current market status (BULL, BEAR, or UNKNOWN).
        """
        try:
            status = self._calculate_regime()
            self._update_status(status)
            return status
        except Exception as e:
            logger.error(f"Failed to evaluate regime: {e}")
            return MarketStatus.UNKNOWN

    def get_current_status(self) -> MarketStatus:
        """Get current market status from DynamoDB.

        Returns:
            Current market status.
        """
        try:
            response = self._dynamodb.get_item(
                TableName=self._config.system_table,
                Key={"key": {"S": "market_status"}},
            )
            item = response.get("Item")
            if item and "value" in item:
                value = item["value"]["S"]
                return MarketStatus(value)
        except (ClientError, ValueError) as e:
            logger.error(f"Failed to get market status: {e}")
        return MarketStatus.UNKNOWN

    def _calculate_regime(self) -> MarketStatus:
        """Calculate regime based on S&P 500 vs 200-day MA.

        Returns:
            BULL if above MA, BEAR if below.
        """
        today = date.today()
        # Fetch enough history for 200-day MA plus buffer
        from datetime import timedelta

        start_date = today - timedelta(days=MA_PERIOD + 30)

        df = self._provider.get_daily_candles(SP500_TICKER, start_date, today)

        if len(df) < MA_PERIOD:
            logger.warning(f"Insufficient data for {MA_PERIOD}-day MA: only {len(df)} records")
            return MarketStatus.UNKNOWN

        # Calculate 200-day Simple Moving Average
        df["sma_200"] = df["close"].rolling(window=MA_PERIOD).mean()

        # Get latest values
        latest = df.iloc[-1]
        current_close = latest["close"]
        current_sma = latest["sma_200"]

        logger.info(
            f"Regime check: {SP500_TICKER} close={current_close:.2f}, SMA200={current_sma:.2f}"
        )

        if pd.isna(current_sma):
            return MarketStatus.UNKNOWN

        if current_close > current_sma:
            logger.info("Market regime: BULL (above 200-day MA)")
            return MarketStatus.BULL
        else:
            logger.info("Market regime: BEAR (below 200-day MA)")
            return MarketStatus.BEAR

    def _update_status(self, status: MarketStatus) -> None:
        """Update market status in DynamoDB.

        Args:
            status: New market status.
        """
        try:
            from datetime import datetime

            self._dynamodb.put_item(
                TableName=self._config.system_table,
                Item={
                    "key": {"S": "market_status"},
                    "value": {"S": status.value},
                    "updated_at": {"S": datetime.utcnow().isoformat()},
                },
            )
            logger.info(f"Updated market_status to {status.value}")
        except ClientError as e:
            logger.error(f"Failed to update market status: {e}")
            raise
