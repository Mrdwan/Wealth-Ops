"""Data Ingestion Lambda Handler.

Triggered daily to ingest market data for all configured assets.
"""

from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.modules.data.manager import DataManager
from src.modules.data.providers.tiingo import TiingoProvider
from src.modules.data.providers.yahoo import YahooProvider
from src.shared.config import load_config
from src.shared.logger import get_logger

logger = get_logger(__name__)


def get_enabled_tickers(config_table: str, region: str) -> list[str]:
    """Scan DynamoDB Config table for enabled tickers.

    Args:
        config_table: Name of the config table.
        region: AWS region.

    Returns:
        List of ticker symbols.
    """
    dynamodb = boto3.client("dynamodb", region_name=region)
    tickers = []
    
    try:
        paginator = dynamodb.get_paginator("scan")
        for page in paginator.paginate(TableName=config_table):
            for item in page.get("Items", []):
                # Basic check for enabled flag if it exists, otherwise assume enabled
                if "enabled" in item and not item["enabled"]["BOOL"]:
                    continue
                
                if "ticker" in item:
                    tickers.append(item["ticker"]["S"])
                    
    except ClientError as e:
        logger.error(f"Failed to scan config table: {e}")
        raise

    return tickers


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for data ingestion.

    Args:
        event: CloudWatch Event or test payload.
        context: Lambda context.

    Returns:
        Execution summary.
    """
    logger.info("Starting Data Ingestion Lambda")
    
    try:
        config = load_config()
        
        # Initialize providers
        tiingo = TiingoProvider(config.tiingo_api_key)
        yahoo = YahooProvider()

        
        # Initialize manager
        manager = DataManager(
            config=config,
            primary_provider=tiingo,
            fallback_provider=yahoo,
        )
        
        # Get tickers to process
        # For now, if no config/tickers exist, we might want to default to a few for testing
        # or just fail if the table is empty.
        tickers = get_enabled_tickers(config.config_table, config.aws_region)
        
        if not tickers:
            logger.warning("No enabled tickers found in configuration.")
            kms_key = "SPY" # Fallback/Default for initial setup if table is empty? 
            # Actually, let's just log and return. The user can populate the table later.
            return {
                "statusCode": 200,
                "body": "No tickers to process.",
                "processed_count": 0
            }

        total_records = 0
        failed_tickers = []
        
        for ticker in tickers:
            try:
                # Default to 50 years for bootstrap, manager handles logic
                records = manager.ingest(ticker)
                total_records += records
            except Exception as e:
                logger.error(f"Failed to ingest {ticker}: {e}")
                failed_tickers.append(ticker)
                # Continue to next ticker
        
        status = "success" if not failed_tickers else "partial_success"
        
        summary = {
            "status": status,
            "total_ingested_records": total_records,
            "processed_tickers": len(tickers) - len(failed_tickers),
            "failed_tickers": failed_tickers,
        }
        
        logger.info(f"Ingestion complete: {summary}")
        
        return {
            "statusCode": 200 if not failed_tickers else 207,
            "body": summary
        }

    except Exception as e:
        logger.exception("Fatal error in Data Ingestion Lambda")
        return {
            "statusCode": 500,
            "body": f"Internal Server Error: {str(e)}"
        }
