"""Market Pulse Lambda Handler.

Triggered daily to check market regime and send status notifications.
"""

from typing import Any

from src.modules.data.providers.tiingo import TiingoProvider
from src.modules.notifications.telegram import TelegramNotifier
from src.modules.regime.filter import RegimeFilter

# We might need yahoo as fallback for regime too if Tiingo fails?
# The RegimeFilter takes a provider.
from src.shared.config import load_config
from src.shared.logger import get_logger

logger = get_logger(__name__)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for market pulse (Regime + Notification).

    Args:
        event: CloudWatch Event or test payload.
        context: Lambda context.

    Returns:
        Execution summary.
    """
    logger.info("Starting Market Pulse Lambda")

    try:
        config = load_config()

        # 1. Evaluate Regime
        # Initialize provider (using Tiingo for S&P500 data)
        provider = TiingoProvider(config.tiingo_api_key)

        regime_filter = RegimeFilter(config, provider)
        market_status = regime_filter.evaluate()

        logger.info(f"Market Status Evaluated: {market_status.value}")

        # 2. Send Telegram Notification
        notifier = TelegramNotifier(config)
        sent = notifier.send_daily_pulse()

        result = {"market_status": market_status.value, "notification_sent": sent}

        logger.info(f"Market Pulse complete: {result}")

        return {"statusCode": 200, "body": result}

    except Exception as e:
        logger.exception("Fatal error in Market Pulse Lambda")
        return {"statusCode": 500, "body": f"Internal Server Error: {str(e)}"}
