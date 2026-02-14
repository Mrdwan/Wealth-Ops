"""Tests for Telegram notifier module."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest
from botocore.exceptions import ClientError

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
        fred_api_key="",
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
        fred_api_key="",
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

    @patch("src.modules.notifications.telegram.httpx.Client")
    def test_send_daily_pulse_success(
        self,
        mock_client_class: MagicMock,
        config: Config,
    ) -> None:
        """Test successful send_daily_pulse flow."""
        mock_dynamodb = MagicMock()
        mock_dynamodb.get_item.side_effect = [
            {"Item": {"key": {"S": "market_status"}, "value": {"S": "BULL"}}},
            {
                "Item": {
                    "asset_type": {"S": "CASH"},
                    "ticker": {"S": "EUR"},
                    "quantity": {"N": "5000"},
                }
            },
        ]
        mock_dynamodb.query.return_value = {"Count": 2}

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = TelegramNotifier(config=config, dynamodb_client=mock_dynamodb)
        result = notifier.send_daily_pulse()

        assert result is True

    def test_get_market_status_no_value_key(self, config: Config) -> None:
        """Test _get_market_status returns UNKNOWN when item has no value key."""
        mock_dynamodb = MagicMock()
        mock_dynamodb.get_item.return_value = {
            "Item": {"key": {"S": "market_status"}}
        }

        notifier = TelegramNotifier(config=config, dynamodb_client=mock_dynamodb)
        result = notifier._get_market_status()

        assert result == MarketStatus.UNKNOWN

    def test_get_cash_balance_no_quantity_key(self, config: Config) -> None:
        """Test _get_cash_balance returns Decimal('0') when item has no quantity key."""
        mock_dynamodb = MagicMock()
        mock_dynamodb.get_item.return_value = {
            "Item": {"asset_type": {"S": "CASH"}, "ticker": {"S": "EUR"}}
        }

        notifier = TelegramNotifier(config=config, dynamodb_client=mock_dynamodb)
        result = notifier._get_cash_balance()

        assert result == Decimal("0")


class TestTelegramErrorHandling:
    """Tests for error handling in TelegramNotifier."""

    def test_send_daily_pulse_exception_returns_false(self, config: Config) -> None:
        """Test send_daily_pulse returns False when gathering data fails."""
        mock_dynamodb = MagicMock()
        mock_dynamodb.get_item.side_effect = Exception("Unexpected error")

        notifier = TelegramNotifier(config=config, dynamodb_client=mock_dynamodb)
        result = notifier.send_daily_pulse()

        assert result is False

    def test_get_market_status_client_error(self, config: Config) -> None:
        """Test _get_market_status returns UNKNOWN on ClientError."""
        mock_dynamodb = MagicMock()
        mock_dynamodb.get_item.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "not found"}},
            "GetItem",
        )

        notifier = TelegramNotifier(config=config, dynamodb_client=mock_dynamodb)
        result = notifier._get_market_status()

        assert result == MarketStatus.UNKNOWN

    def test_get_market_status_invalid_value(self, config: Config) -> None:
        """Test _get_market_status returns UNKNOWN for invalid enum value."""
        mock_dynamodb = MagicMock()
        mock_dynamodb.get_item.return_value = {
            "Item": {"key": {"S": "market_status"}, "value": {"S": "INVALID_STATUS"}}
        }

        notifier = TelegramNotifier(config=config, dynamodb_client=mock_dynamodb)
        result = notifier._get_market_status()

        assert result == MarketStatus.UNKNOWN

    def test_get_cash_balance_client_error(self, config: Config) -> None:
        """Test _get_cash_balance returns Decimal('0') on ClientError."""
        mock_dynamodb = MagicMock()
        mock_dynamodb.get_item.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "not found"}},
            "GetItem",
        )

        notifier = TelegramNotifier(config=config, dynamodb_client=mock_dynamodb)
        result = notifier._get_cash_balance()

        assert result == Decimal("0")

    def test_count_open_positions_client_error(self, config: Config) -> None:
        """Test _count_open_positions returns 0 on ClientError."""
        mock_dynamodb = MagicMock()
        mock_dynamodb.query.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "not found"}},
            "Query",
        )

        notifier = TelegramNotifier(config=config, dynamodb_client=mock_dynamodb)
        result = notifier._count_open_positions()

        assert result == 0

    @patch("src.modules.notifications.telegram.httpx.Client")
    def test_send_message_http_error(
        self,
        mock_client_class: MagicMock,
        config: Config,
    ) -> None:
        """Test _send_message returns False on HTTP error."""
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.HTTPError("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = TelegramNotifier(config=config, dynamodb_client=MagicMock())
        result = notifier._send_message("Test message")

        assert result is False


class TestSendReply:
    """Tests for send_reply() method."""

    @patch("src.modules.notifications.telegram.httpx.Client")
    def test_send_reply_success(
        self,
        mock_client_class: MagicMock,
        config: Config,
    ) -> None:
        """Test successful reply sending."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = TelegramNotifier(config=config, dynamodb_client=MagicMock())
        result = notifier.send_reply("123456", "Test reply")

        assert result is True
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[1]["json"]["chat_id"] == "123456"
        assert call_kwargs[1]["json"]["text"] == "Test reply"

    def test_send_reply_no_token_returns_false(
        self,
        config_no_telegram: Config,
    ) -> None:
        """Test send_reply returns False when bot token is not configured."""
        notifier = TelegramNotifier(
            config=config_no_telegram,
            dynamodb_client=MagicMock(),
        )
        result = notifier.send_reply("123456", "Test reply")

        assert result is False

    @patch("src.modules.notifications.telegram.httpx.Client")
    def test_send_reply_http_error_returns_false(
        self,
        mock_client_class: MagicMock,
        config: Config,
    ) -> None:
        """Test send_reply returns False on HTTP error."""
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.HTTPError("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = TelegramNotifier(config=config, dynamodb_client=MagicMock())
        result = notifier.send_reply("123456", "Test reply")

        assert result is False


class TestSendSignalCard:
    """Tests for send_signal_card() method."""

    @patch("src.modules.notifications.telegram.httpx.Client")
    def test_send_signal_card_success(
        self,
        mock_client_class: MagicMock,
        config: Config,
    ) -> None:
        """Test successful signal card sending."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = TelegramNotifier(config=config, dynamodb_client=MagicMock())
        result = notifier.send_signal_card("🟢 SIGNAL — LONG XAU/USD")

        assert result is True
        mock_client.post.assert_called_once()

    def test_send_signal_card_no_credentials(
        self,
        config_no_telegram: Config,
    ) -> None:
        """Test signal card returns False without credentials."""
        notifier = TelegramNotifier(
            config=config_no_telegram,
            dynamodb_client=MagicMock(),
        )
        result = notifier.send_signal_card("Test signal")

        assert result is False

    @patch("src.modules.notifications.telegram.httpx.Client")
    def test_send_signal_card_http_error(
        self,
        mock_client_class: MagicMock,
        config: Config,
    ) -> None:
        """Test signal card returns False on HTTP error."""
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.HTTPError("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = TelegramNotifier(config=config, dynamodb_client=MagicMock())
        result = notifier.send_signal_card("Test signal")

        assert result is False
