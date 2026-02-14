"""Staleness Guard — enforces data freshness for market-level sources.

Checks DynamoDB timestamps for VIX, SPY, and DXY data to ensure
signal pipeline operates on fresh data. When any source is stale
(>24h), the guard defaults to FAIL and sends a Telegram alert.

Architecture ref: ARCHITECTURE.md Section 8.B (Guards 1-2).
Roadmap ref: Step 2A.5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.shared.config import Config
from src.shared.logger import get_logger

logger = get_logger(__name__)

# Default staleness threshold for market-level data (hours)
STALENESS_THRESHOLD_HOURS = 24

# Sources to check and their DynamoDB key patterns
_MARKET_SOURCES: list[tuple[str, str, str]] = [
    # (label, dynamo_table_type, dynamo_key)
    ("VIX", "system", "macro_staleness_VIXCLS"),
    ("SPY", "config", "SPY"),
    ("DXY", "config", "UUP"),
]


@dataclass(frozen=True)
class SourceStaleness:
    """Staleness check result for a single data source.

    Attributes:
        label: Human-readable source name (VIX, SPY, DXY).
        is_stale: True if data exceeds staleness threshold.
        last_updated: Timestamp of last update (None if never updated).
        age_hours: Data age in hours (None if never updated).
    """

    label: str
    is_stale: bool
    last_updated: datetime | None
    age_hours: float | None


@dataclass(frozen=True)
class StalenessResult:
    """Aggregated staleness check result for all market-level sources.

    Attributes:
        passed: True only if ALL sources are fresh.
        sources: Per-source staleness details.
        alert_message: Pre-formatted Telegram alert (None if all fresh).
    """

    passed: bool
    sources: list[SourceStaleness] = field(default_factory=list)
    alert_message: str | None = None


def _format_staleness_alert(stale_sources: list[SourceStaleness]) -> str:
    """Format a Telegram alert message for stale data sources.

    Args:
        stale_sources: List of stale source results.

    Returns:
        Formatted alert message string.
    """
    lines = [
        "⚠️ WEALTH-OPS DATA STALENESS ALERT",
        "",
        "The following market-level data sources are STALE (>24h):",
        "",
    ]
    for src in stale_sources:
        if src.age_hours is not None:
            lines.append(f"  🔴 {src.label}: {src.age_hours:.1f}h old")
        else:
            lines.append(f"  🔴 {src.label}: NEVER UPDATED")
    lines.append("")
    lines.append("Signal pipeline guards default to FAIL until data is refreshed.")
    lines.append("Run data ingestion to resolve.")
    return "\n".join(lines)


class StalenessGuard:
    """Checks data freshness for VIX, SPY, and DXY.

    Uses the same DynamoDB staleness timestamps set by:
    - ``MacroDataManager._update_staleness()`` for VIX (VIXCLS)
    - ``DataManager._update_last_updated()`` for SPY and DXY (UUP)

    When data is stale (>24h), the guard returns FAIL and optionally
    sends a Telegram alert.
    """

    def __init__(
        self,
        config: Config,
        dynamodb_client: Any | None = None,
    ) -> None:
        """Initialize StalenessGuard.

        Args:
            config: Application configuration.
            dynamodb_client: Optional boto3 DynamoDB client (for testing).
        """
        self._config = config
        self._dynamodb = dynamodb_client or boto3.client(
            "dynamodb", region_name=config.aws_region
        )

    def check(self) -> StalenessResult:
        """Check staleness of all market-level data sources.

        Returns:
            StalenessResult with per-source details and overall pass/fail.
        """
        results: list[SourceStaleness] = []

        for label, table_type, key in _MARKET_SOURCES:
            result = self._check_source(label, table_type, key)
            results.append(result)

        stale_sources = [s for s in results if s.is_stale]
        passed = len(stale_sources) == 0

        alert_message: str | None = None
        if not passed:
            alert_message = _format_staleness_alert(stale_sources)
            stale_labels = ", ".join(s.label for s in stale_sources)
            logger.warning(f"Staleness guard FAILED: {stale_labels}")
        else:
            logger.info("Staleness guard PASSED: all sources fresh")

        return StalenessResult(
            passed=passed,
            sources=results,
            alert_message=alert_message,
        )

    def _check_source(
        self, label: str, table_type: str, key: str
    ) -> SourceStaleness:
        """Check staleness for a single data source.

        Args:
            label: Human-readable label (VIX, SPY, DXY).
            table_type: 'system' or 'config' — determines lookup strategy.
            key: DynamoDB key for lookup.

        Returns:
            SourceStaleness result for this source.
        """
        try:
            last_updated = self._get_last_updated(table_type, key)

            if last_updated is None:
                logger.warning(f"{label}: no staleness timestamp found")
                return SourceStaleness(
                    label=label,
                    is_stale=True,
                    last_updated=None,
                    age_hours=None,
                )

            age = datetime.now(timezone.utc) - last_updated
            age_hours = age.total_seconds() / 3600.0
            is_stale = age > timedelta(hours=STALENESS_THRESHOLD_HOURS)

            return SourceStaleness(
                label=label,
                is_stale=is_stale,
                last_updated=last_updated,
                age_hours=age_hours,
            )

        except ClientError as e:
            logger.error(f"DynamoDB error checking {label} staleness: {e}")
            return SourceStaleness(
                label=label,
                is_stale=True,
                last_updated=None,
                age_hours=None,
            )

    def _get_last_updated(
        self, table_type: str, key: str
    ) -> datetime | None:
        """Read the last-updated timestamp from DynamoDB.

        For 'system' table (VIX): reads ``macro_staleness_VIXCLS`` key,
        ``updated_at`` attribute (ISO format datetime).

        For 'config' table (SPY/DXY): reads ticker key,
        ``last_updated_date`` attribute (ISO format date, converted to
        midnight UTC).

        Args:
            table_type: 'system' or 'config'.
            key: DynamoDB key value.

        Returns:
            Datetime of last update (UTC), or None if not found.
        """
        if table_type == "system":
            return self._get_system_timestamp(key)
        return self._get_config_timestamp(key)

    def _get_system_timestamp(self, key: str) -> datetime | None:
        """Read timestamp from System table (macro staleness pattern).

        Args:
            key: DynamoDB key (e.g. 'macro_staleness_VIXCLS').

        Returns:
            Datetime of last update, or None.
        """
        response = self._dynamodb.get_item(
            TableName=self._config.system_table,
            Key={"key": {"S": key}},
        )
        item = response.get("Item")
        if not item or "updated_at" not in item:
            return None
        return datetime.fromisoformat(item["updated_at"]["S"])

    def _get_config_timestamp(self, key: str) -> datetime | None:
        """Read timestamp from Config table (market data pattern).

        The Config table stores ``last_updated_date`` as an ISO date
        string. We convert to midnight UTC for age comparison.

        Args:
            key: DynamoDB ticker key (e.g. 'SPY').

        Returns:
            Datetime of last update (midnight UTC), or None.
        """
        response = self._dynamodb.get_item(
            TableName=self._config.config_table,
            Key={"ticker": {"S": key}},
        )
        item = response.get("Item")
        if not item or "last_updated_date" not in item:
            return None
        date_str = item["last_updated_date"]["S"]
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
