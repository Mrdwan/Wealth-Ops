"""Telegram Notifier - Daily Briefing via Telegram Bot.

Sends daily pulse messages to a configured Telegram chat.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import boto3
import httpx
from botocore.exceptions import ClientError

from src.modules.regime.filter import MarketStatus
from src.shared.config import Config
from src.shared.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DailyPulse:
    """Data for daily briefing message."""

    date: date
    market_status: MarketStatus
    cash_balance: Decimal
    open_positions: int


class TelegramNotifier:
    """Telegram bot for sending notifications.

    Uses the Telegram Bot API to send messages to a configured chat.
    """

    def __init__(
        self,
        config: Config,
        dynamodb_client: Any | None = None,
    ) -> None:
        """Initialize TelegramNotifier.

        Args:
            config: Application configuration.
            dynamodb_client: Optional boto3 DynamoDB client (for testing).
        """
        self._config = config
        self._dynamodb = dynamodb_client or boto3.client("dynamodb", region_name=config.aws_region)
        self._api_url = f"https://api.telegram.org/bot{config.telegram_bot_token}"

    def send_daily_pulse(self) -> bool:
        """Gather data and send daily pulse message.

        Returns:
            True if message sent successfully, False otherwise.
        """
        try:
            pulse = self._gather_pulse_data()
            message = self._format_pulse_message(pulse)
            return self._send_message(message)
        except Exception as e:
            logger.error(f"Failed to send daily pulse: {e}")
            return False

    def send_signal_card(self, card_text: str) -> bool:
        """Send a formatted signal card via Telegram.

        Args:
            card_text: Pre-formatted signal card message text.

        Returns:
            True if sent successfully, False otherwise.
        """
        logger.info("Sending signal card via Telegram")
        return self._send_message(card_text)

    def _gather_pulse_data(self) -> DailyPulse:
        """Gather data for daily pulse from DynamoDB.

        Returns:
            DailyPulse with current state.
        """
        market_status = self._get_market_status()
        cash_balance = self._get_cash_balance()
        open_positions = self._count_open_positions()

        return DailyPulse(
            date=date.today(),
            market_status=market_status,
            cash_balance=cash_balance,
            open_positions=open_positions,
        )

    def _get_market_status(self) -> MarketStatus:
        """Get market status from System table."""
        try:
            response = self._dynamodb.get_item(
                TableName=self._config.system_table,
                Key={"key": {"S": "market_status"}},
            )
            item = response.get("Item")
            if item and "value" in item:
                return MarketStatus(item["value"]["S"])
        except (ClientError, ValueError) as e:
            logger.error(f"Failed to get market status: {e}")
        return MarketStatus.UNKNOWN

    def _get_cash_balance(self) -> Decimal:
        """Get cash balance from Portfolio table."""
        try:
            response = self._dynamodb.get_item(
                TableName=self._config.portfolio_table,
                Key={
                    "asset_type": {"S": "CASH"},
                    "ticker": {"S": "EUR"},
                },
            )
            item = response.get("Item")
            if item and "quantity" in item:
                return Decimal(item["quantity"]["N"])
        except ClientError as e:
            logger.error(f"Failed to get cash balance: {e}")
        return Decimal("0")

    def _count_open_positions(self) -> int:
        """Count open stock positions from Portfolio table."""
        try:
            response = self._dynamodb.query(
                TableName=self._config.portfolio_table,
                KeyConditionExpression="asset_type = :t",
                ExpressionAttributeValues={":t": {"S": "STOCK"}},
                Select="COUNT",
            )
            return response.get("Count", 0)
        except ClientError as e:
            logger.error(f"Failed to count positions: {e}")
        return 0

    def _format_pulse_message(self, pulse: DailyPulse) -> str:
        """Format pulse data into Telegram message.

        Args:
            pulse: Daily pulse data.

        Returns:
            Formatted message string.
        """
        status_emoji = {
            MarketStatus.BULL: "🟢",
            MarketStatus.BEAR: "🔴",
            MarketStatus.UNKNOWN: "⚪",
        }

        return f"""🏛️ *Wealth-Ops Daily Pulse*
📅 {pulse.date.isoformat()}

📊 Market Status: {status_emoji[pulse.market_status]} {pulse.market_status.value}
💰 Cash: €{pulse.cash_balance:,.2f}
📈 Open Positions: {pulse.open_positions}

Have a great trading day\\!"""

    def send_reply(self, chat_id: str, text: str) -> bool:
        """Send a reply to a specific chat.

        Used by the webhook handler for two-way command responses.

        Args:
            chat_id: Telegram chat ID to reply to.
            text: Message text (plain text, no markdown).

        Returns:
            True if sent successfully.
        """
        if not self._config.telegram_bot_token:
            logger.warning("Telegram bot token not configured, skipping reply")
            return False

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{self._api_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                    },
                )
                response.raise_for_status()
                logger.info(f"Reply sent to chat {chat_id}")
                return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to send Telegram reply: {e}")
            return False

    def _send_message(self, text: str) -> bool:
        """Send message via Telegram Bot API.

        Args:
            text: Message text (Markdown format).

        Returns:
            True if sent successfully.
        """
        if not self._config.telegram_bot_token or not self._config.telegram_chat_id:
            logger.warning("Telegram credentials not configured, skipping notification")
            return False

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{self._api_url}/sendMessage",
                    json={
                        "chat_id": self._config.telegram_chat_id,
                        "text": text,
                        "parse_mode": "MarkdownV2",
                    },
                )
                response.raise_for_status()
                logger.info("Daily pulse sent to Telegram")
                return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
