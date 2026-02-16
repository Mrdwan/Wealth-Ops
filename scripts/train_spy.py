#!/usr/bin/env python3
"""
Manual run script for SPY training pipeline.
Simulates a training run using the new One-Asset One-Model pipeline.
"""
import sys
import os
import pandas as pd
import numpy as np
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.modules.training.pipeline import TrainingPipeline
from src.modules.training.types import TrainingConfig

def create_mock_data():
    """Generates 2 years of random OHLCV data."""
    dates = pd.date_range(start="2022-01-01", end="2023-12-31", freq="D")
    n = len(dates)
    
    # Random walk for price
    price = 100 + np.cumsum(np.random.randn(n))
    
    df = pd.DataFrame({
        "open": price + np.random.randn(n),
        "high": price + 2 + np.random.randn(n),
        "low": price - 2 + np.random.randn(n),
        "close": price + np.random.randn(n),
        "volume": np.random.randint(1000, 10000, n).astype(float)
    }, index=dates)
    return df

def main():
    print("Initializing Training Pipeline for SPY...")
    
    # Mock DataManager
    data_manager = MagicMock()
    print("Fetching data (Mocked)...")
    data_manager.get_history.return_value = create_mock_data()
    
    # Config
    config = TrainingConfig(
        max_depth=3,
        n_estimators=100,
        target_window=5,
        target_threshold=0.02
    )
    
    pipeline = TrainingPipeline(data_manager, config=config, output_dir="models_manual")
    
    print("Running pipeline...")
    artifact = pipeline.run("SPY")
    
    if artifact:
        print("\nSUCCESS: Model Trained.")
        print(f"Ticker: {artifact.ticker}")
        print(f"Metrics: {artifact.metrics}")
        print(f"Feature Names: {artifact.feature_names[:5]}... ({len(artifact.feature_names)} total)")
        print(f"Artifact saved to: {artifact.model_path}")
    else:
        print("\nFAILURE: Pipeline returned None.")

if __name__ == "__main__":
    main()
