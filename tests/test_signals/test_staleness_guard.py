"""Tests for StalenessGuard.

All DynamoDB calls are mocked via MagicMock. No network calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.modules.signals.staleness_guard import (
    STALENESS_THRESHOLD_HOURS,
    SourceStaleness,
    StalenessGuard,
    StalenessResult,
    _format_staleness_alert,
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


def _fresh_timestamp() -> str:
    """Return an ISO timestamp 1 hour ago (fresh)."""
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


def _stale_timestamp() -> str:
    """Return an ISO timestamp 25 hours ago (stale)."""
    return (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()


def _fresh_date() -> str:
    """Return today's date as ISO string (fresh for config table)."""
    return datetime.now(timezone.utc).date().isoformat()


def _stale_date() -> str:
    """Return a date 3 days ago as ISO string (stale for config table)."""
    return (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()


def _build_mock_dynamodb(
    *,
    vix_timestamp: str | None = None,
    spy_date: str | None = None,
    dxy_date: str | None = None,
) -> MagicMock:
    """Build a mock DynamoDB client with configurable responses.

    Args:
        vix_timestamp: ISO datetime for VIX staleness (None = missing).
        spy_date: ISO date for SPY last_updated_date (None = missing).
        dxy_date: ISO date for DXY last_updated_date (None = missing).

    Returns:
        MagicMock DynamoDB client.
    """
    mock = MagicMock()

    def get_item_side_effect(**kwargs: object) -> dict[str, object]:
        table = kwargs.get("TableName", "")
        key = kwargs.get("Key", {})

        # System table (VIX)
        if table == "test-system":
            assert isinstance(key, dict)
            if vix_timestamp is not None:
                return {
                    "Item": {
                        "key": {"S": "macro_staleness_VIXCLS"},
                        "updated_at": {"S": vix_timestamp},
                    }
                }
            return {}

        # Config table (SPY / DXY)
        if table == "test-config":
            assert isinstance(key, dict)
            ticker_key = key.get("ticker", {})
            assert isinstance(ticker_key, dict)
            ticker = ticker_key.get("S", "")

            if ticker == "SPY" and spy_date is not None:
                return {
                    "Item": {
                        "ticker": {"S": "SPY"},
                        "last_updated_date": {"S": spy_date},
                    }
                }
            if ticker == "UUP" and dxy_date is not None:
                return {
                    "Item": {
                        "ticker": {"S": "UUP"},
                        "last_updated_date": {"S": dxy_date},
                    }
                }
            return {}

        return {}

    mock.get_item.side_effect = get_item_side_effect
    return mock


class TestStalenessGuard:
    """Tests for StalenessGuard.check()."""

    def test_all_fresh_passes(self, config: Config) -> None:
        """All sources fresh → passed=True, no alert."""
        mock_db = _build_mock_dynamodb(
            vix_timestamp=_fresh_timestamp(),
            spy_date=_fresh_date(),
            dxy_date=_fresh_date(),
        )

        guard = StalenessGuard(config=config, dynamodb_client=mock_db)
        result = guard.check()

        assert result.passed is True
        assert result.alert_message is None
        assert len(result.sources) == 3
        assert all(not s.is_stale for s in result.sources)

    def test_vix_stale_fails(self, config: Config) -> None:
        """VIX stale → passed=False, alert mentions VIX."""
        mock_db = _build_mock_dynamodb(
            vix_timestamp=_stale_timestamp(),
            spy_date=_fresh_date(),
            dxy_date=_fresh_date(),
        )

        guard = StalenessGuard(config=config, dynamodb_client=mock_db)
        result = guard.check()

        assert result.passed is False
        assert result.alert_message is not None
        assert "VIX" in result.alert_message
        stale = [s for s in result.sources if s.is_stale]
        assert len(stale) == 1
        assert stale[0].label == "VIX"

    def test_spy_stale_fails(self, config: Config) -> None:
        """SPY stale → passed=False, alert mentions SPY."""
        mock_db = _build_mock_dynamodb(
            vix_timestamp=_fresh_timestamp(),
            spy_date=_stale_date(),
            dxy_date=_fresh_date(),
        )

        guard = StalenessGuard(config=config, dynamodb_client=mock_db)
        result = guard.check()

        assert result.passed is False
        assert result.alert_message is not None
        assert "SPY" in result.alert_message

    def test_dxy_stale_fails(self, config: Config) -> None:
        """DXY stale → passed=False, alert mentions DXY."""
        mock_db = _build_mock_dynamodb(
            vix_timestamp=_fresh_timestamp(),
            spy_date=_fresh_date(),
            dxy_date=_stale_date(),
        )

        guard = StalenessGuard(config=config, dynamodb_client=mock_db)
        result = guard.check()

        assert result.passed is False
        assert result.alert_message is not None
        assert "DXY" in result.alert_message

    def test_multiple_stale_combined_alert(self, config: Config) -> None:
        """Multiple stale → combined alert with all labels."""
        mock_db = _build_mock_dynamodb(
            vix_timestamp=_stale_timestamp(),
            spy_date=_stale_date(),
            dxy_date=_stale_date(),
        )

        guard = StalenessGuard(config=config, dynamodb_client=mock_db)
        result = guard.check()

        assert result.passed is False
        assert result.alert_message is not None
        assert "VIX" in result.alert_message
        assert "SPY" in result.alert_message
        assert "DXY" in result.alert_message
        stale = [s for s in result.sources if s.is_stale]
        assert len(stale) == 3

    def test_no_timestamp_defaults_to_stale(self, config: Config) -> None:
        """Missing timestamp → stale (safe default)."""
        mock_db = _build_mock_dynamodb(
            vix_timestamp=None,  # never updated
            spy_date=_fresh_date(),
            dxy_date=_fresh_date(),
        )

        guard = StalenessGuard(config=config, dynamodb_client=mock_db)
        result = guard.check()

        assert result.passed is False
        vix_source = next(s for s in result.sources if s.label == "VIX")
        assert vix_source.is_stale is True
        assert vix_source.last_updated is None
        assert vix_source.age_hours is None

    def test_dynamodb_error_defaults_to_stale(self, config: Config) -> None:
        """DynamoDB ClientError → stale (safe default)."""
        mock_db = MagicMock()
        mock_db.get_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "fail"}},
            "GetItem",
        )

        guard = StalenessGuard(config=config, dynamodb_client=mock_db)
        result = guard.check()

        assert result.passed is False
        assert all(s.is_stale for s in result.sources)

    def test_source_staleness_has_age_hours(self, config: Config) -> None:
        """Fresh source should report age in hours."""
        mock_db = _build_mock_dynamodb(
            vix_timestamp=_fresh_timestamp(),
            spy_date=_fresh_date(),
            dxy_date=_fresh_date(),
        )

        guard = StalenessGuard(config=config, dynamodb_client=mock_db)
        result = guard.check()

        vix_source = next(s for s in result.sources if s.label == "VIX")
        assert vix_source.age_hours is not None
        assert vix_source.age_hours < STALENESS_THRESHOLD_HOURS

    def test_config_timestamp_naive_gets_utc(self, config: Config) -> None:
        """Config table date (naive) should be handled as UTC."""
        # Fresh date — should not be stale
        mock_db = _build_mock_dynamodb(
            vix_timestamp=_fresh_timestamp(),
            spy_date=_fresh_date(),
            dxy_date=_fresh_date(),
        )

        guard = StalenessGuard(config=config, dynamodb_client=mock_db)
        result = guard.check()

        spy_source = next(s for s in result.sources if s.label == "SPY")
        assert spy_source.last_updated is not None
        assert spy_source.last_updated.tzinfo is not None

    def test_config_item_without_last_updated_date(self, config: Config) -> None:
        """Config item exists but lacks last_updated_date → stale."""
        mock_db = MagicMock()

        def get_item_side_effect(**kwargs: object) -> dict[str, object]:
            table = kwargs.get("TableName", "")
            key = kwargs.get("Key", {})
            if table == "test-system":
                return {
                    "Item": {
                        "key": {"S": "macro_staleness_VIXCLS"},
                        "updated_at": {"S": _fresh_timestamp()},
                    }
                }
            if table == "test-config":
                assert isinstance(key, dict)
                ticker_key = key.get("ticker", {})
                assert isinstance(ticker_key, dict)
                ticker = ticker_key.get("S", "")
                if ticker == "SPY":
                    # Item exists but no last_updated_date field
                    return {"Item": {"ticker": {"S": "SPY"}}}
                if ticker == "UUP":
                    return {
                        "Item": {
                            "ticker": {"S": "UUP"},
                            "last_updated_date": {"S": _fresh_date()},
                        }
                    }
            return {}

        mock_db.get_item.side_effect = get_item_side_effect

        guard = StalenessGuard(config=config, dynamodb_client=mock_db)
        result = guard.check()

        spy_source = next(s for s in result.sources if s.label == "SPY")
        assert spy_source.is_stale is True
        assert spy_source.last_updated is None

    def test_config_timestamp_with_timezone(self, config: Config) -> None:
        """Config table date with timezone info should be preserved."""
        tz_aware_date = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()

        mock_db = MagicMock()

        def get_item_side_effect(**kwargs: object) -> dict[str, object]:
            table = kwargs.get("TableName", "")
            key = kwargs.get("Key", {})
            if table == "test-system":
                return {
                    "Item": {
                        "key": {"S": "macro_staleness_VIXCLS"},
                        "updated_at": {"S": _fresh_timestamp()},
                    }
                }
            if table == "test-config":
                assert isinstance(key, dict)
                ticker_key = key.get("ticker", {})
                assert isinstance(ticker_key, dict)
                ticker = ticker_key.get("S", "")
                # Both SPY and UUP use timezone-aware datetime strings
                if ticker in ("SPY", "UUP"):
                    return {
                        "Item": {
                            "ticker": {"S": ticker},
                            "last_updated_date": {"S": tz_aware_date},
                        }
                    }
            return {}

        mock_db.get_item.side_effect = get_item_side_effect

        guard = StalenessGuard(config=config, dynamodb_client=mock_db)
        result = guard.check()

        spy_source = next(s for s in result.sources if s.label == "SPY")
        assert spy_source.is_stale is False
        assert spy_source.last_updated is not None
        assert spy_source.last_updated.tzinfo is not None


class TestFormatStalenessAlert:
    """Tests for _format_staleness_alert."""

    def test_single_stale_source(self) -> None:
        """Alert for a single stale source."""
        src = SourceStaleness(
            label="VIX", is_stale=True, last_updated=None, age_hours=None
        )
        msg = _format_staleness_alert([src])

        assert "STALENESS ALERT" in msg
        assert "VIX" in msg
        assert "NEVER UPDATED" in msg

    def test_stale_with_age(self) -> None:
        """Alert with known age shows hours."""
        src = SourceStaleness(
            label="SPY",
            is_stale=True,
            last_updated=datetime.now(timezone.utc) - timedelta(hours=48),
            age_hours=48.0,
        )
        msg = _format_staleness_alert([src])

        assert "48.0h old" in msg
        assert "SPY" in msg

    def test_multiple_sources(self) -> None:
        """Alert for multiple stale sources lists all."""
        sources = [
            SourceStaleness(label="VIX", is_stale=True, last_updated=None, age_hours=None),
            SourceStaleness(label="DXY", is_stale=True, last_updated=None, age_hours=25.0),
        ]
        msg = _format_staleness_alert(sources)

        assert "VIX" in msg
        assert "DXY" in msg
        assert "Signal pipeline guards default to FAIL" in msg
