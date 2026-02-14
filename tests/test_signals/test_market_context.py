"""Tests for MarketContext and MarketDataLoader.

All S3 calls are mocked via MagicMock. No network calls, deterministic data.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pandas as pd
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest
from botocore.exceptions import ClientError

from src.modules.signals.market_context import (
    MIN_BARS_SMA,
    MarketContext,
    MarketDataLoader,
)
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
        tiingo_api_key="",
        fred_api_key="",
        telegram_bot_token="",
        telegram_chat_id="",
        environment="test",
    )


def _make_ohlcv_parquet_bytes(n: int, start_price: float = 100.0) -> bytes:
    """Create an OHLCV parquet file as bytes with n rows.

    Args:
        n: Number of rows.
        start_price: Starting close price.

    Returns:
        Parquet file as bytes.
    """
    dates = pd.bdate_range(start="2023-01-03", periods=n)
    close = [start_price + i * 0.1 for i in range(n)]
    df = pd.DataFrame(
        {
            "open": [c - 0.2 for c in close],
            "high": [c + 0.5 for c in close],
            "low": [c - 0.5 for c in close],
            "close": close,
            "volume": [1_000_000.0] * n,
        },
        index=dates,
    )
    table = pa.Table.from_pandas(df)
    buf = pa.BufferOutputStream()
    pq.write_table(table, buf)
    return buf.getvalue().to_pybytes()


def _make_macro_parquet_bytes(values: list[float]) -> bytes:
    """Create a macro (date, value) parquet file as bytes.

    Args:
        values: List of observation values.

    Returns:
        Parquet file as bytes.
    """
    dates = pd.bdate_range(start="2023-01-03", periods=len(values))
    df = pd.DataFrame({"value": values}, index=dates)
    table = pa.Table.from_pandas(df)
    buf = pa.BufferOutputStream()
    pq.write_table(table, buf)
    return buf.getvalue().to_pybytes()


def _make_s3_get_body(data: bytes) -> dict[str, object]:
    """Create a mock S3 get_object response.

    Args:
        data: Parquet bytes.

    Returns:
        Dict matching S3 get_object response shape.
    """
    body = MagicMock()
    body.read.return_value = data
    return {"Body": body}


class TestMarketContext:
    """Tests for the MarketContext dataclass."""

    def test_spy_above_sma200_true(self) -> None:
        """SPY above SMA200 should return True."""
        ctx = MarketContext(
            vix_close=18.0, spy_close=450.0, spy_sma200=440.0,
            dxy_close=100.0, dxy_sma200=102.0,
        )
        assert ctx.spy_above_sma200 is True

    def test_spy_above_sma200_false(self) -> None:
        """SPY below SMA200 should return False."""
        ctx = MarketContext(
            vix_close=18.0, spy_close=430.0, spy_sma200=440.0,
            dxy_close=100.0, dxy_sma200=102.0,
        )
        assert ctx.spy_above_sma200 is False

    def test_spy_above_sma200_nan(self) -> None:
        """SPY SMA200 NaN should return None."""
        ctx = MarketContext(
            vix_close=18.0, spy_close=450.0, spy_sma200=float("nan"),
            dxy_close=100.0, dxy_sma200=102.0,
        )
        assert ctx.spy_above_sma200 is None

    def test_spy_above_sma200_close_nan(self) -> None:
        """SPY close NaN should return None."""
        ctx = MarketContext(
            vix_close=18.0, spy_close=float("nan"), spy_sma200=440.0,
            dxy_close=100.0, dxy_sma200=102.0,
        )
        assert ctx.spy_above_sma200 is None

    def test_dxy_below_sma200_true(self) -> None:
        """DXY below SMA200 (weak dollar) should return True."""
        ctx = MarketContext(
            vix_close=18.0, spy_close=450.0, spy_sma200=440.0,
            dxy_close=99.0, dxy_sma200=102.0,
        )
        assert ctx.dxy_below_sma200 is True

    def test_dxy_below_sma200_false(self) -> None:
        """DXY above SMA200 should return False."""
        ctx = MarketContext(
            vix_close=18.0, spy_close=450.0, spy_sma200=440.0,
            dxy_close=105.0, dxy_sma200=102.0,
        )
        assert ctx.dxy_below_sma200 is False

    def test_dxy_below_sma200_nan(self) -> None:
        """DXY SMA200 NaN should return None."""
        ctx = MarketContext(
            vix_close=18.0, spy_close=450.0, spy_sma200=440.0,
            dxy_close=105.0, dxy_sma200=float("nan"),
        )
        assert ctx.dxy_below_sma200 is None

    def test_dxy_below_sma200_close_nan(self) -> None:
        """DXY close NaN should return None."""
        ctx = MarketContext(
            vix_close=18.0, spy_close=450.0, spy_sma200=440.0,
            dxy_close=float("nan"), dxy_sma200=102.0,
        )
        assert ctx.dxy_below_sma200 is None

    def test_vix_below_panic_true(self) -> None:
        """VIX below 30 should pass panic guard."""
        ctx = MarketContext(
            vix_close=18.0, spy_close=450.0, spy_sma200=440.0,
            dxy_close=100.0, dxy_sma200=102.0,
        )
        assert ctx.vix_below_panic is True

    def test_vix_below_panic_false(self) -> None:
        """VIX above 30 should fail panic guard."""
        ctx = MarketContext(
            vix_close=35.0, spy_close=450.0, spy_sma200=440.0,
            dxy_close=100.0, dxy_sma200=102.0,
        )
        assert ctx.vix_below_panic is False

    def test_vix_below_panic_nan(self) -> None:
        """VIX NaN should return None."""
        ctx = MarketContext(
            vix_close=float("nan"), spy_close=450.0, spy_sma200=440.0,
            dxy_close=100.0, dxy_sma200=102.0,
        )
        assert ctx.vix_below_panic is None


class TestMarketDataLoader:
    """Tests for MarketDataLoader."""

    def test_load_happy_path(self, config: Config) -> None:
        """Test full load with VIX, SPY, and DXY all available."""
        n = 250  # enough for SMA(200)
        spy_parquet = _make_ohlcv_parquet_bytes(n, start_price=400.0)
        dxy_parquet = _make_ohlcv_parquet_bytes(n, start_price=100.0)
        vix_parquet = _make_macro_parquet_bytes([18.5] * n)

        mock_s3 = MagicMock()

        # list_objects_v2 for SPY and DXY
        mock_s3.list_objects_v2.side_effect = [
            {"Contents": [{"Key": "ohlcv/stocks/SPY/daily/2023_2024.parquet"}]},
            {"Contents": [{"Key": "ohlcv/indices/UUP/daily/2023_2024.parquet"}]},
        ]

        # get_object for VIX, SPY, DXY
        mock_s3.get_object.side_effect = [
            _make_s3_get_body(vix_parquet),   # VIX
            _make_s3_get_body(spy_parquet),   # SPY
            _make_s3_get_body(dxy_parquet),   # DXY
        ]

        loader = MarketDataLoader(config=config, s3_client=mock_s3)
        ctx = loader.load()

        assert not pd.isna(ctx.vix_close)
        assert not pd.isna(ctx.spy_close)
        assert not pd.isna(ctx.spy_sma200)
        assert not pd.isna(ctx.dxy_close)
        assert not pd.isna(ctx.dxy_sma200)

    def test_load_vix_s3_error_returns_nan(self, config: Config) -> None:
        """VIX S3 error should return NaN for VIX close."""
        n = 250
        spy_parquet = _make_ohlcv_parquet_bytes(n)
        dxy_parquet = _make_ohlcv_parquet_bytes(n)

        mock_s3 = MagicMock()
        mock_s3.get_object.side_effect = [
            ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "not found"}},
                "GetObject",
            ),
            _make_s3_get_body(spy_parquet),
            _make_s3_get_body(dxy_parquet),
        ]
        mock_s3.list_objects_v2.side_effect = [
            {"Contents": [{"Key": "ohlcv/stocks/SPY/daily/f.parquet"}]},
            {"Contents": [{"Key": "ohlcv/indices/UUP/daily/f.parquet"}]},
        ]

        loader = MarketDataLoader(config=config, s3_client=mock_s3)
        ctx = loader.load()

        assert pd.isna(ctx.vix_close)
        assert not pd.isna(ctx.spy_close)

    def test_load_spy_no_parquets_returns_nan(self, config: Config) -> None:
        """No SPY parquet files → NaN for SPY close and SMA."""
        vix_parquet = _make_macro_parquet_bytes([20.0])

        mock_s3 = MagicMock()
        mock_s3.get_object.side_effect = [
            _make_s3_get_body(vix_parquet),
            # DXY
            _make_s3_get_body(_make_ohlcv_parquet_bytes(250)),
        ]
        mock_s3.list_objects_v2.side_effect = [
            {"Contents": []},  # SPY — empty
            {"Contents": [{"Key": "ohlcv/indices/UUP/daily/f.parquet"}]},
        ]

        loader = MarketDataLoader(config=config, s3_client=mock_s3)
        ctx = loader.load()

        assert pd.isna(ctx.spy_close)
        assert pd.isna(ctx.spy_sma200)

    def test_load_insufficient_bars_for_sma(self, config: Config) -> None:
        """Fewer than 200 bars → SMA is NaN, close is available."""
        n = 50
        spy_parquet = _make_ohlcv_parquet_bytes(n, start_price=400.0)
        dxy_parquet = _make_ohlcv_parquet_bytes(n, start_price=100.0)
        vix_parquet = _make_macro_parquet_bytes([18.0] * n)

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.side_effect = [
            {"Contents": [{"Key": "ohlcv/stocks/SPY/daily/f.parquet"}]},
            {"Contents": [{"Key": "ohlcv/indices/UUP/daily/f.parquet"}]},
        ]
        mock_s3.get_object.side_effect = [
            _make_s3_get_body(vix_parquet),
            _make_s3_get_body(spy_parquet),
            _make_s3_get_body(dxy_parquet),
        ]

        loader = MarketDataLoader(config=config, s3_client=mock_s3)
        ctx = loader.load()

        assert not pd.isna(ctx.spy_close)
        assert pd.isna(ctx.spy_sma200)
        assert not pd.isna(ctx.dxy_close)
        assert pd.isna(ctx.dxy_sma200)

    def test_load_empty_vix_parquet(self, config: Config) -> None:
        """Empty VIX parquet → NaN."""
        empty_vix = _make_macro_parquet_bytes([])
        spy_parquet = _make_ohlcv_parquet_bytes(250)
        dxy_parquet = _make_ohlcv_parquet_bytes(250)

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.side_effect = [
            {"Contents": [{"Key": "ohlcv/stocks/SPY/daily/f.parquet"}]},
            {"Contents": [{"Key": "ohlcv/indices/UUP/daily/f.parquet"}]},
        ]
        mock_s3.get_object.side_effect = [
            _make_s3_get_body(empty_vix),
            _make_s3_get_body(spy_parquet),
            _make_s3_get_body(dxy_parquet),
        ]

        loader = MarketDataLoader(config=config, s3_client=mock_s3)
        ctx = loader.load()

        assert pd.isna(ctx.vix_close)

    def test_load_empty_ohlcv_parquet(self, config: Config) -> None:
        """Empty SPY parquet → NaN for SPY close and SMA."""
        # Create an empty OHLCV parquet
        empty_df = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
            dtype=float,
        )
        table = pa.Table.from_pandas(empty_df)
        buf = pa.BufferOutputStream()
        pq.write_table(table, buf)
        empty_parquet = buf.getvalue().to_pybytes()

        vix_parquet = _make_macro_parquet_bytes([20.0])
        dxy_parquet = _make_ohlcv_parquet_bytes(250)

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.side_effect = [
            {"Contents": [{"Key": "ohlcv/stocks/SPY/daily/f.parquet"}]},
            {"Contents": [{"Key": "ohlcv/indices/UUP/daily/f.parquet"}]},
        ]
        mock_s3.get_object.side_effect = [
            _make_s3_get_body(vix_parquet),
            _make_s3_get_body(empty_parquet),
            _make_s3_get_body(dxy_parquet),
        ]

        loader = MarketDataLoader(config=config, s3_client=mock_s3)
        ctx = loader.load()

        assert pd.isna(ctx.spy_close)
        assert pd.isna(ctx.spy_sma200)

    def test_load_dxy_s3_error_returns_nan(self, config: Config) -> None:
        """DXY S3 list error should return NaN for DXY close and SMA."""
        vix_parquet = _make_macro_parquet_bytes([20.0])
        spy_parquet = _make_ohlcv_parquet_bytes(250)

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.side_effect = [
            {"Contents": [{"Key": "ohlcv/stocks/SPY/daily/f.parquet"}]},
            ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "nope"}},
                "ListObjectsV2",
            ),
        ]
        mock_s3.get_object.side_effect = [
            _make_s3_get_body(vix_parquet),
            _make_s3_get_body(spy_parquet),
        ]

        loader = MarketDataLoader(config=config, s3_client=mock_s3)
        ctx = loader.load()

        assert pd.isna(ctx.dxy_close)
        assert pd.isna(ctx.dxy_sma200)
        assert not pd.isna(ctx.spy_close)

    def test_find_latest_parquet_selects_last_sorted(self, config: Config) -> None:
        """Should pick the lexicographically last parquet file."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "ohlcv/stocks/SPY/daily/2022-01_2022-12.parquet"},
                {"Key": "ohlcv/stocks/SPY/daily/2023-01_2023-12.parquet"},
                {"Key": "ohlcv/stocks/SPY/daily/2021-01_2021-12.parquet"},
            ]
        }

        loader = MarketDataLoader(config=config, s3_client=mock_s3)
        key = loader._find_latest_parquet("ohlcv/stocks/SPY/daily/", "SPY")

        assert key == "ohlcv/stocks/SPY/daily/2023-01_2023-12.parquet"

    def test_find_latest_parquet_no_files(self, config: Config) -> None:
        """No parquet files → returns None."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": []}

        loader = MarketDataLoader(config=config, s3_client=mock_s3)
        key = loader._find_latest_parquet("ohlcv/stocks/SPY/daily/", "SPY")

        assert key is None

    def test_find_latest_parquet_filters_non_parquet(self, config: Config) -> None:
        """Non-parquet files should be ignored."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "ohlcv/stocks/SPY/daily/readme.txt"},
                {"Key": "ohlcv/stocks/SPY/daily/data.parquet"},
            ]
        }

        loader = MarketDataLoader(config=config, s3_client=mock_s3)
        key = loader._find_latest_parquet("ohlcv/stocks/SPY/daily/", "SPY")

        assert key == "ohlcv/stocks/SPY/daily/data.parquet"

    def test_find_latest_parquet_s3_error_raises(self, config: Config) -> None:
        """S3 list error in _find_latest_parquet should raise ClientError."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "fail"}},
            "ListObjectsV2",
        )

        loader = MarketDataLoader(config=config, s3_client=mock_s3)
        with pytest.raises(ClientError):
            loader._find_latest_parquet("ohlcv/stocks/SPY/daily/", "SPY")

    def test_find_latest_parquet_no_contents_key(self, config: Config) -> None:
        """Response without Contents key → returns None."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {}

        loader = MarketDataLoader(config=config, s3_client=mock_s3)
        key = loader._find_latest_parquet("ohlcv/stocks/SPY/daily/", "SPY")

        assert key is None
