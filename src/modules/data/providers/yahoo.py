"""Yahoo Finance Market Data Provider.

Fallback data source using yfinance library (unofficial scraper).
"""

from datetime import date

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]

from src.modules.data.protocols import ProviderError
from src.shared.logger import get_logger

logger = get_logger(__name__)


class YahooProvider:
    """Yahoo Finance market data provider (Fallback).

    Uses yfinance library which scrapes Yahoo Finance.
    Be aware: may be rate-limited or blocked with heavy usage.
    """

    @property
    def name(self) -> str:
        """Provider name."""
        return "Yahoo"

    def get_daily_candles(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch daily OHLCV candles from Yahoo Finance.

        Args:
            ticker: Stock symbol (e.g., 'AAPL').
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            Normalized DataFrame with OHLCV data.

        Raises:
            ProviderError: If Yahoo Finance fails.
        """
        logger.info(
            "Fetching data from Yahoo Finance (fallback)",
            extra={"ticker": ticker, "start": str(start_date), "end": str(end_date)},
        )

        try:
            # yfinance end_date is exclusive, so add 1 day
            end_date_exclusive = pd.Timestamp(end_date) + pd.Timedelta(days=1)

            stock = yf.Ticker(ticker)
            df = stock.history(
                start=start_date.isoformat(),
                end=end_date_exclusive.strftime("%Y-%m-%d"),
                interval="1d",
            )

            if df.empty:
                raise ProviderError(self.name, ticker, "No data returned")

            return self._normalize(df)

        except Exception as e:
            if isinstance(e, ProviderError):
                raise
            raise ProviderError(self.name, ticker, str(e)) from e

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize yfinance response to standard schema.

        Args:
            df: Raw yfinance DataFrame.

        Returns:
            Normalized DataFrame.
        """
        # yfinance uses 'Close' (capitalized) and 'Adj Close'
        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
                "Adj Close": "adjusted_close",
            }
        )

        # Convert index to date
        df.index = df.index.date  # type: ignore[attr-defined]
        df.index.name = "date"

        # Select standard columns
        standard_cols = ["open", "high", "low", "close", "volume", "adjusted_close"]
        available_cols = [col for col in standard_cols if col in df.columns]

        return df[available_cols].sort_index()
