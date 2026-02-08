"""Data Manager - Market Data Orchestrator.

Handles provider failover, gap-fill logic, and S3/DynamoDB persistence.
"""

from datetime import date, timedelta
from enum import Enum
from typing import Any

import boto3
import pandas as pd
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from botocore.exceptions import ClientError

from src.modules.data.protocols import MarketDataProvider, ProviderError
from src.shared.config import Config
from src.shared.logger import get_logger

logger = get_logger(__name__)


class FetchMode(Enum):
    """Determines how much data to fetch based on existing state."""

    BOOTSTRAP = "bootstrap"  # No data exists, fetch max history
    DAILY_DRIP = "daily_drip"  # Data is current, fetch today only
    GAP_FILL = "gap_fill"  # Missing days, fetch the gap


class DataManager:
    """Orchestrates market data fetching with failover and gap-fill logic.

    This is the main entry point for data ingestion. It:
    1. Reads state from DynamoDB to determine what data is needed
    2. Tries the primary provider, falls back if it fails
    3. Saves data to S3 as Parquet
    4. Updates DynamoDB with new state
    """

    def __init__(
        self,
        config: Config,
        primary_provider: MarketDataProvider,
        fallback_provider: MarketDataProvider,
        s3_client: Any | None = None,
        dynamodb_client: Any | None = None,
    ) -> None:
        """Initialize DataManager.

        Args:
            config: Application configuration.
            primary_provider: Primary market data provider (e.g., Tiingo).
            fallback_provider: Fallback provider (e.g., Yahoo).
            s3_client: Optional boto3 S3 client (for testing).
            dynamodb_client: Optional boto3 DynamoDB client (for testing).
        """
        self._config = config
        self._primary = primary_provider
        self._fallback = fallback_provider
        self._s3 = s3_client or boto3.client("s3", region_name=config.aws_region)
        self._dynamodb = dynamodb_client or boto3.client("dynamodb", region_name=config.aws_region)

    def ingest(self, ticker: str, max_history_years: int = 50) -> int:
        """Ingest market data for a ticker with gap-fill logic.

        Args:
            ticker: Stock symbol (e.g., 'AAPL').
            max_history_years: Max years to fetch in bootstrap mode.

        Returns:
            Number of records ingested.

        Raises:
            ProviderError: If all providers fail.
        """
        last_updated = self._get_last_updated(ticker)
        today = date.today()

        mode, start_date, end_date = self._determine_fetch_params(
            last_updated, today, max_history_years
        )

        logger.info(
            f"Ingesting {ticker}",
            extra={
                "mode": mode.value,
                "start": str(start_date),
                "end": str(end_date),
                "last_updated": str(last_updated) if last_updated else None,
            },
        )

        # Skip if already up to date
        if mode == FetchMode.DAILY_DRIP and start_date > end_date:
            logger.info(f"{ticker} is already up to date")
            return 0

        # Fetch with failover
        df = self._fetch_with_failover(ticker, start_date, end_date)

        if df.empty:
            logger.warning(f"No data returned for {ticker}")
            return 0

        # Save to S3
        self._save_to_s3(ticker, df)

        # Update DynamoDB
        new_last_updated = df.index.max()
        self._update_last_updated(ticker, new_last_updated)

        record_count = len(df)
        logger.info(f"Ingested {record_count} records for {ticker}")
        return record_count

    def _determine_fetch_params(
        self,
        last_updated: date | None,
        today: date,
        max_history_years: int,
    ) -> tuple[FetchMode, date, date]:
        """Determine fetch mode and date range.

        Args:
            last_updated: Last known data date, or None if never fetched.
            today: Current date.
            max_history_years: Max years for bootstrap.

        Returns:
            Tuple of (mode, start_date, end_date).
        """
        yesterday = today - timedelta(days=1)

        if last_updated is None:
            # Bootstrap: fetch max history
            start = today - timedelta(days=365 * max_history_years)
            return FetchMode.BOOTSTRAP, start, yesterday

        if last_updated >= yesterday:
            # Already up to date
            return FetchMode.DAILY_DRIP, today, yesterday

        if last_updated == yesterday - timedelta(days=1):
            # Normal daily drip
            return FetchMode.DAILY_DRIP, yesterday, yesterday

        # Gap fill: missing multiple days
        start = last_updated + timedelta(days=1)
        return FetchMode.GAP_FILL, start, yesterday

    def _fetch_with_failover(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch data with provider failover.

        Args:
            ticker: Stock symbol.
            start_date: Fetch start date.
            end_date: Fetch end date.

        Returns:
            DataFrame with OHLCV data.

        Raises:
            ProviderError: If all providers fail.
        """
        try:
            return self._primary.get_daily_candles(ticker, start_date, end_date)
        except ProviderError as e:
            logger.warning(f"Primary provider failed: {e}, trying fallback")

        try:
            return self._fallback.get_daily_candles(ticker, start_date, end_date)
        except ProviderError as e:
            logger.error(f"Fallback provider also failed: {e}")
            raise

    def _get_last_updated(self, ticker: str) -> date | None:
        """Get last updated date from DynamoDB Config table.

        Args:
            ticker: Stock symbol.

        Returns:
            Last updated date, or None if ticker not found.
        """
        try:
            response = self._dynamodb.get_item(
                TableName=self._config.config_table,
                Key={"ticker": {"S": ticker}},
            )
            item = response.get("Item")
            if item and "last_updated_date" in item:
                return date.fromisoformat(item["last_updated_date"]["S"])
        except ClientError as e:
            logger.error(f"DynamoDB error: {e}")
        return None

    def _update_last_updated(self, ticker: str, last_date: date) -> None:
        """Update last updated date in DynamoDB Config table.

        Args:
            ticker: Stock symbol.
            last_date: New last updated date.
        """
        try:
            self._dynamodb.update_item(
                TableName=self._config.config_table,
                Key={"ticker": {"S": ticker}},
                UpdateExpression="SET last_updated_date = :d",
                ExpressionAttributeValues={":d": {"S": last_date.isoformat()}},
            )
        except ClientError as e:
            logger.error(f"Failed to update DynamoDB: {e}")
            raise

    def _save_to_s3(self, ticker: str, df: pd.DataFrame) -> None:
        """Save DataFrame to S3 as Parquet.

        Args:
            ticker: Stock symbol.
            df: DataFrame to save.
        """
        # Convert to parquet bytes
        table = pa.Table.from_pandas(df)
        buffer = pa.BufferOutputStream()
        pq.write_table(table, buffer)
        parquet_bytes = buffer.getvalue().to_pybytes()

        # Determine S3 key
        min_date = df.index.min()
        max_date = df.index.max()
        key = f"raw/{ticker}/{min_date}_{max_date}.parquet"

        try:
            self._s3.put_object(
                Bucket=self._config.s3_bucket,
                Key=key,
                Body=parquet_bytes,
            )
            logger.info(f"Saved {len(df)} records to s3://{self._config.s3_bucket}/{key}")
        except ClientError as e:
            logger.error(f"Failed to save to S3: {e}")
            raise
