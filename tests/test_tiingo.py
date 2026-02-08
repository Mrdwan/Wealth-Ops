"""Tests for Tiingo market data provider."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.modules.data.protocols import ProviderError
from src.modules.data.providers.tiingo import TiingoProvider


@pytest.fixture
def provider() -> TiingoProvider:
    """Create a TiingoProvider instance for testing."""
    return TiingoProvider(api_key="test-api-key")


@pytest.fixture
def sample_tiingo_response() -> list[dict[str, object]]:
    """Sample Tiingo API response."""
    return [
        {
            "date": "2024-01-02T00:00:00.000Z",
            "open": 150.0,
            "high": 155.0,
            "low": 149.0,
            "close": 154.0,
            "volume": 1000000,
            "adjClose": 154.0,
        },
        {
            "date": "2024-01-03T00:00:00.000Z",
            "open": 154.0,
            "high": 158.0,
            "low": 153.0,
            "close": 157.0,
            "volume": 1100000,
            "adjClose": 157.0,
        },
    ]


class TestTiingoProvider:
    """Tests for TiingoProvider."""

    def test_name_property(self, provider: TiingoProvider) -> None:
        """Test provider name."""
        assert provider.name == "Tiingo"

    @patch("src.modules.data.providers.tiingo.httpx.Client")
    def test_get_daily_candles_success(
        self,
        mock_client_class: MagicMock,
        provider: TiingoProvider,
        sample_tiingo_response: list[dict[str, object]],
    ) -> None:
        """Test successful data fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_tiingo_response
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        df = provider.get_daily_candles(
            ticker="AAPL",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 3),
        )

        assert len(df) == 2
        assert "close" in df.columns
        assert "adjusted_close" in df.columns
        assert df.iloc[0]["close"] == 154.0

    @patch("src.modules.data.providers.tiingo.httpx.Client")
    def test_get_daily_candles_empty_response(
        self,
        mock_client_class: MagicMock,
        provider: TiingoProvider,
    ) -> None:
        """Test empty response raises ProviderError."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        with pytest.raises(ProviderError) as exc_info:
            provider.get_daily_candles(
                ticker="INVALID",
                start_date=date(2024, 1, 2),
                end_date=date(2024, 1, 3),
            )

        assert "No data returned" in str(exc_info.value)

    @patch("src.modules.data.providers.tiingo.httpx.Client")
    def test_get_daily_candles_http_error(
        self,
        mock_client_class: MagicMock,
        provider: TiingoProvider,
    ) -> None:
        """Test HTTP error raises ProviderError."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            message="Unauthorized",
            request=MagicMock(),
            response=mock_response,
        )
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        with pytest.raises(ProviderError) as exc_info:
            provider.get_daily_candles(
                ticker="AAPL",
                start_date=date(2024, 1, 2),
                end_date=date(2024, 1, 3),
            )

        assert "Tiingo" in str(exc_info.value)
