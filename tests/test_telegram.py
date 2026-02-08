"""Tests for Telegram notifier module."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.modules.notifications.telegram import DailyPulse, TelegramNotifier
from src.modules.regime.filter import MarketStatus
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
        telegram_bot_token="test-bot-token",
        telegram_chat_id="123456",
        environment="test",
    )


@pytest.fixture
def config_no_telegram() -> Config:
    """Create config without Telegram credentials."""
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


class TestTelegramNotifier:
    """Tests for TelegramNotifier."""

    def test_format_pulse_message_bull(self, config: Config) -> None:
        """Test message formatting for BULL market."""
        notifier = TelegramNotifier(config=config, dynamodb_client=MagicMock())

        pulse = DailyPulse(
            date=date(2024, 1, 15),
            market_status=MarketStatus.BULL,
            cash_balance=Decimal("12450.00"),
            open_positions=3,
        )

        message = notifier._format_pulse_message(pulse)

        assert "2024-01-15" in message
        assert "BULL" in message
        assert "🟢" in message
        assert "12,450.00" in message
        assert "3" in message

    def test_format_pulse_message_bear(self, config: Config) -> None:
        """Test message formatting for BEAR market."""
        notifier = TelegramNotifier(config=config, dynamodb_client=MagicMock())

        pulse = DailyPulse(
            date=date(2024, 1, 15),
            market_status=MarketStatus.BEAR,
            cash_balance=Decimal("5000.00"),
            open_positions=0,
        )

        message = notifier._format_pulse_message(pulse)

        assert "BEAR" in message
        assert "🔴" in message

    def test_gather_pulse_data_from_dynamodb(self, config: Config) -> None:
        """Test gathering pulse data from DynamoDB."""
        mock_dynamodb = MagicMock()

        # Mock system table response (market status)
        mock_dynamodb.get_item.side_effect = [
            {"Item": {"key": {"S": "market_status"}, "value": {"S": "BULL"}}},
            {
                "Item": {
                    "asset_type": {"S": "CASH"},
                    "ticker": {"S": "EUR"},
                    "quantity": {"N": "10000"},
                }
            },
        ]

        # Mock portfolio query response (positions count)
        mock_dynamodb.query.return_value = {"Count": 5}

        notifier = TelegramNotifier(config=config, dynamodb_client=mock_dynamodb)
        pulse = notifier._gather_pulse_data()

        assert pulse.market_status == MarketStatus.BULL
        assert pulse.cash_balance == Decimal("10000")
        assert pulse.open_positions == 5

    @patch("src.modules.notifications.telegram.httpx.Client")
    def test_send_message_success(
        self,
        mock_client_class: MagicMock,
        config: Config,
    ) -> None:
        """Test successful message sending."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = TelegramNotifier(config=config, dynamodb_client=MagicMock())
        result = notifier._send_message("Test message")

        assert result is True
        mock_client.post.assert_called_once()

    def test_send_message_skipped_without_credentials(
        self,
        config_no_telegram: Config,
    ) -> None:
        """Test message sending skipped without credentials."""
        notifier = TelegramNotifier(
            config=config_no_telegram,
            dynamodb_client=MagicMock(),
        )
        result = notifier._send_message("Test message")

        assert result is False
