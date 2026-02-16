import pytest
import pandas as pd
import numpy as np
from src.modules.training.data_prep import TrainingDataPrep
from src.shared.profiles import AssetProfile

@pytest.fixture
def sample_data():
    dates = pd.date_range(start="2023-01-01", periods=100, freq="D")
    df = pd.DataFrame({
        "open": 100 + np.random.randn(100),
        "high": 105 + np.random.randn(100),
        "low": 95 + np.random.randn(100),
        "close": 100 + np.random.randn(100),
        "volume": 1000 + np.random.randn(100)
    }, index=dates)
    return df

def test_create_target_logic(sample_data):
    prep = TrainingDataPrep()
    
    # Create controlled data
    df = pd.DataFrame({
        "close": [100, 100, 100, 100, 100, 100],
        "high":  [100, 101, 102, 105, 100, 100] # Breakout at index 3 (105)
    }, index=pd.date_range("2023-01-01", periods=6))
    
    # Threshold 3% -> Target 103.
    # Window 5.
    # t=0: Future Max (t+1..t+5) = Max(101, 102, 105, 100, 100) = 105.
    # 105 > 103 -> 1.
    
    target = prep.create_target(df, window=2, threshold=0.03)
    
    # t=0 (Price 100, Target 103). Future (t+1..t+2): [101, 102]. Max 102.
    # 102 < 103 -> 0.
    assert target.iloc[0] == 0
    
    # t=1 (Price 100). Future (t+1..t+2): [102, 105]. Max 105.
    # 105 > 103 -> 1.
    assert target.iloc[1] == 1
    
    # t=2 (Price 100). Future (t+1..t+2): [105, 100]. Max 105.
    # 105 > 103 -> 1.
    assert target.iloc[2] == 1
    
    # Check NaN at end
    assert np.isnan(target.iloc[-1])
    assert np.isnan(target.iloc[-2])

def create_mock_profile(**kwargs):
    defaults = {
        "asset_class": "EQUITY",
        "regime_index": "SPY",
        "regime_direction": "BULL",
        "vix_guard": True,
        "event_guard": True,
        "macro_event_guard": False,
        "volume_features": True,
        "benchmark_index": "SPY",
        "concentration_group": "TEST",
        "broker": "PAPER",
        "tax_rate": 0.0,
        "data_source": "TIINGO"
    }
    defaults.update(kwargs)
    return AssetProfile(**defaults)

def test_create_feature_vector_empty():
    prep = TrainingDataPrep()
    profile = create_mock_profile()
    features = prep.create_feature_vector(pd.DataFrame(), profile)
    assert features.empty

def test_create_feature_vector(sample_data):
    prep = TrainingDataPrep()
    profile = create_mock_profile(volume_features=True)
    
    features = prep.create_feature_vector(sample_data, profile)
    
    assert not features.empty
    assert "rsi_14" in features.columns
    assert "day_of_week" in features.columns
    assert "volume_ratio" in features.columns # Correct name

def test_create_feature_vector_no_volume(sample_data):
    prep = TrainingDataPrep()
    profile = create_mock_profile(asset_class="FOREX", volume_features=False)
    
    features = prep.create_feature_vector(sample_data, profile)
    
    # Should NOT have volume features (obv, volume_ratio)
    # But might have original 'volume' column from input df?
    # FeatureEngine.compute returns df.copy(). So yes.
    # We check for generated features.
    
    generated_vol_cols = ["obv", "volume_ratio"]
    for col in generated_vol_cols:
        assert col not in features.columns
