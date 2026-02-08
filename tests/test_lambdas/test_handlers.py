"""Unit tests for Lambda handlers."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.lambdas.data_ingestion import handler as data_ingestion_handler
from src.lambdas.market_pulse import handler as market_pulse_handler
from src.modules.regime.filter import MarketStatus


@pytest.fixture
def mock_config() -> Any:
    """Mock configuration."""
    with patch("src.lambdas.data_ingestion.load_config") as mock:
        config = MagicMock()
        config.aws_region = "us-east-1"
        config.config_table = "wealth-ops-config-dev"
        mock.return_value = config
        yield mock


@pytest.fixture
def mock_boto3_dynamodb() -> Any:
    """Mock boto3 dynamo client."""
    with patch("src.lambdas.data_ingestion.boto3.client") as mock:
        yield mock


def test_data_ingestion_success(mock_config: Any, mock_boto3_dynamodb: Any) -> None:
    """Test successful data ingestion."""
    # Mock DynamoDB scan response
    mock_dynamodb = mock_boto3_dynamodb.return_value
    mock_paginator = MagicMock()
    mock_dynamodb.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {"Items": [{"ticker": {"S": "AAPL"}, "enabled": {"BOOL": True}}]}
    ]

    # Mock DataManager
    with patch("src.lambdas.data_ingestion.DataManager") as MockManager:
        manager = MockManager.return_value
        manager.ingest.return_value = 100  # 100 records ingested

        # Run handler
        response = data_ingestion_handler({}, {})

        assert response["statusCode"] == 200
        assert response["body"]["total_ingested_records"] == 100
        assert response["body"]["processed_tickers"] == 1
        assert response["body"]["failed_tickers"] == []


def test_data_ingestion_no_tickers(mock_config: Any, mock_boto3_dynamodb: Any) -> None:
    """Test ingestion with no enabled tickers."""
    mock_dynamodb = mock_boto3_dynamodb.return_value
    mock_paginator = MagicMock()
    mock_dynamodb.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [{"Items": []}]

    with patch("src.lambdas.data_ingestion.DataManager"):
        response = data_ingestion_handler({}, {})

        assert response["statusCode"] == 200
        assert "No tickers" in response["body"]


def test_data_ingestion_partial_failure(mock_config: Any, mock_boto3_dynamodb: Any) -> None:
    """Test ingestion where one ticker fails."""
    mock_dynamodb = mock_boto3_dynamodb.return_value
    mock_paginator = MagicMock()
    mock_dynamodb.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {
            "Items": [
                {"ticker": {"S": "AAPL"}, "enabled": {"BOOL": True}},
                {"ticker": {"S": "GOOGL"}, "enabled": {"BOOL": True}},
            ]
        }
    ]

    with patch("src.lambdas.data_ingestion.DataManager") as MockManager:
        manager = MockManager.return_value
        # First call succeeds, second fails
        manager.ingest.side_effect = [100, Exception("API Error")]

        response = data_ingestion_handler({}, {})

        assert response["statusCode"] == 207  # Partial content
        assert response["body"]["status"] == "partial_success"
        assert response["body"]["total_ingested_records"] == 100
        assert response["body"]["processed_tickers"] == 1
        assert "GOOGL" in response["body"]["failed_tickers"]


def test_market_pulse_success() -> None:
    """Test successful market pulse."""
    with patch("src.lambdas.market_pulse.load_config"), patch(
        "src.lambdas.market_pulse.TiingoProvider"
    ), patch("src.lambdas.market_pulse.RegimeFilter") as MockFilter, patch(
        "src.lambdas.market_pulse.TelegramNotifier"
    ) as MockNotifier:
        # Mock Regime
        regime = MockFilter.return_value
        regime.evaluate.return_value = MarketStatus.BULL

        # Mock Notifier
        notifier = MockNotifier.return_value
        notifier.send_daily_pulse.return_value = True

        response = market_pulse_handler({}, {})

        assert response["statusCode"] == 200
        assert response["body"]["market_status"] == "BULL"
        assert response["body"]["notification_sent"] is True


def test_market_pulse_failure() -> None:
    """Test failure in market pulse."""
    with patch("src.lambdas.market_pulse.load_config"), patch(
        "src.lambdas.market_pulse.TiingoProvider"
    ), patch("src.lambdas.market_pulse.RegimeFilter") as MockFilter:
        # Mock exception
        regime = MockFilter.return_value
        regime.evaluate.side_effect = Exception("S3 Error")

        response = market_pulse_handler({}, {})

        assert response["statusCode"] == 500
        assert "Internal Server Error" in response["body"]
