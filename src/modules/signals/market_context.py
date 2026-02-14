"""Market-Level Data Integration — context and loader.

Reads VIX (FRED), SPY, and DXY (UUP proxy) data from S3 and exposes
a frozen ``MarketContext`` for downstream signal pipeline consumption.

Architecture ref: ARCHITECTURE.md Sections 3.4, 8.B (Guards 1-2).
Roadmap ref: Step 2A.5.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import boto3
import pandas as pd
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from botocore.exceptions import ClientError

from src.shared.config import Config
from src.shared.logger import get_logger

logger = get_logger(__name__)

# SMA period used for regime gate calculations
SMA_PERIOD = 200

# Minimum bars required to compute a meaningful SMA(200)
MIN_BARS_SMA = SMA_PERIOD

# S3 path constants
_VIX_S3_KEY = "ohlcv/macro/VIXCLS.parquet"


@dataclass(frozen=True)
class MarketContext:
    """Snapshot of market-level data for the signal pipeline.

    Attributes:
        vix_close: Latest VIX closing value (NaN if unavailable).
        spy_close: Latest SPY closing price (NaN if unavailable).
        spy_sma200: SPY 200-day simple moving average (NaN if < 200 bars).
        dxy_close: Latest DXY (UUP proxy) closing price (NaN if unavailable).
        dxy_sma200: DXY 200-day SMA (NaN if < 200 bars).
    """

    vix_close: float
    spy_close: float
    spy_sma200: float
    dxy_close: float
    dxy_sma200: float

    @property
    def spy_above_sma200(self) -> bool | None:
        """True if SPY close > SMA200, None if SMA200 unavailable."""
        if pd.isna(self.spy_sma200) or pd.isna(self.spy_close):
            return None
        return bool(self.spy_close > self.spy_sma200)

    @property
    def dxy_below_sma200(self) -> bool | None:
        """True if DXY close < SMA200 (weak dollar), None if unavailable."""
        if pd.isna(self.dxy_sma200) or pd.isna(self.dxy_close):
            return None
        return bool(self.dxy_close < self.dxy_sma200)

    @property
    def vix_below_panic(self) -> bool | None:
        """True if VIX < 30 (panic guard passes), None if unavailable."""
        if pd.isna(self.vix_close):
            return None
        return bool(self.vix_close < 30.0)


class MarketDataLoader:
    """Loads VIX, SPY, and DXY data from S3 to build a MarketContext.

    Expects data to already be ingested by Phase 1 data pipelines.
    SPY and DXY (UUP) are stored as OHLCV parquets; VIX as macro parquet.
    """

    def __init__(
        self,
        config: Config,
        s3_client: Any | None = None,
    ) -> None:
        """Initialize MarketDataLoader.

        Args:
            config: Application configuration.
            s3_client: Optional boto3 S3 client (for testing).
        """
        self._config = config
        self._s3 = s3_client or boto3.client(
            "s3", region_name=config.aws_region
        )

    def load(self) -> MarketContext:
        """Load all market-level data and return a MarketContext.

        Returns:
            MarketContext with latest VIX, SPY, and DXY values.
            Individual fields are NaN when data is missing.
        """
        vix_close = self._load_vix()
        spy_close, spy_sma200 = self._load_ohlcv_with_sma(
            "ohlcv/stocks/SPY/daily/", "SPY"
        )
        dxy_close, dxy_sma200 = self._load_ohlcv_with_sma(
            "ohlcv/indices/UUP/daily/", "DXY"
        )

        ctx = MarketContext(
            vix_close=vix_close,
            spy_close=spy_close,
            spy_sma200=spy_sma200,
            dxy_close=dxy_close,
            dxy_sma200=dxy_sma200,
        )
        logger.info(
            f"MarketContext loaded: VIX={vix_close:.2f}, "
            f"SPY={spy_close:.2f} (SMA200={spy_sma200:.2f}), "
            f"DXY={dxy_close:.2f} (SMA200={dxy_sma200:.2f})"
        )
        return ctx

    def _load_vix(self) -> float:
        """Load latest VIX value from S3 macro parquet.

        Returns:
            Latest VIX close value, or NaN on failure.
        """
        try:
            df = self._read_parquet(_VIX_S3_KEY)
            if df.empty:
                logger.warning("VIX parquet is empty")
                return float("nan")
            return float(df["value"].iloc[-1])
        except ClientError as e:
            logger.error(f"Failed to load VIX from S3: {e}")
            return float("nan")

    def _load_ohlcv_with_sma(
        self, prefix: str, label: str
    ) -> tuple[float, float]:
        """Load OHLCV data from S3 and compute SMA(200).

        Lists objects under the prefix, reads the latest parquet,
        and computes the 200-day SMA on the close column.

        Args:
            prefix: S3 key prefix (e.g. 'ohlcv/stocks/SPY/daily/').
            label: Human-readable label for logging.

        Returns:
            Tuple of (latest_close, sma200). Either may be NaN.
        """
        nan = float("nan")
        try:
            key = self._find_latest_parquet(prefix, label)
            if key is None:
                return nan, nan

            df = self._read_parquet(key)
            if df.empty:
                logger.warning(f"{label} parquet is empty")
                return nan, nan

            latest_close = float(df["close"].iloc[-1])

            if len(df) < MIN_BARS_SMA:
                logger.warning(
                    f"{label}: only {len(df)} bars, need {MIN_BARS_SMA} "
                    f"for SMA({SMA_PERIOD})"
                )
                return latest_close, nan

            sma = float(
                df["close"].rolling(window=SMA_PERIOD).mean().iloc[-1]
            )
            return latest_close, sma

        except ClientError as e:
            logger.error(f"Failed to load {label} from S3: {e}")
            return nan, nan

    def _find_latest_parquet(
        self, prefix: str, label: str
    ) -> str | None:
        """Find the latest parquet file under an S3 prefix.

        Args:
            prefix: S3 key prefix.
            label: Human-readable label for logging.

        Returns:
            S3 key of the latest parquet, or None if none found.
        """
        try:
            response = self._s3.list_objects_v2(
                Bucket=self._config.s3_bucket,
                Prefix=prefix,
            )
            contents = response.get("Contents", [])
            parquets = [
                obj["Key"]
                for obj in contents
                if obj["Key"].endswith(".parquet")
            ]
            if not parquets:
                logger.warning(f"No parquet files found for {label} at {prefix}")
                return None
            # Sort lexicographically — date-based keys sort naturally
            parquets.sort()
            return parquets[-1]
        except ClientError as e:
            logger.error(f"Failed to list S3 objects for {label}: {e}")
            raise

    def _read_parquet(self, key: str) -> pd.DataFrame:
        """Read a parquet file from S3.

        Args:
            key: S3 object key.

        Returns:
            DataFrame from the parquet file.

        Raises:
            ClientError: If S3 read fails.
        """
        response = self._s3.get_object(
            Bucket=self._config.s3_bucket,
            Key=key,
        )
        body = response["Body"].read()
        table = pq.read_table(io.BytesIO(body))
        return table.to_pandas()
