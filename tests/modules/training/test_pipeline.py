import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from src.modules.training.pipeline import TrainingPipeline
from src.modules.training.types import TrainingConfig, ModelArtifact
from src.shared.profiles import AssetProfile

@pytest.fixture
def mock_data_manager():
    dm = MagicMock()
    # Return a DF with enough data
    dates = pd.date_range(start="2020-01-01", periods=300, freq="D")
    df = pd.DataFrame({
        "open": 100 + np.random.randn(300),
        "high": 105 + np.random.randn(300),
        "low": 95 + np.random.randn(300),
        "close": 100 + np.random.randn(300),
        "volume": 1000 + np.random.randn(300)
    }, index=dates)
    dm.get_history.return_value = df
    return dm

def test_pipeline_run_success(mock_data_manager):
    # Mock XGBoostTrainer to avoid real training time
    with patch("src.modules.training.pipeline.XGBoostTrainer") as MockTrainer:
        trainer_instance = MockTrainer.return_value
        trainer_instance.train.return_value = ModelArtifact(
            ticker="TEST",
            model_path="dummy/path",
            metrics={"auc": 0.8},
            calibration_curve={},
            feature_names=["rsi_14"],
            config=TrainingConfig()
        )
        
        pipeline = TrainingPipeline(mock_data_manager)
        
        # Use a tmp dir for output
        with patch("src.modules.training.pipeline.os.makedirs"), \
             patch("builtins.open", new_callable=MagicMock) as mock_open, \
             patch("json.dump") as mock_json_dump:
                 
            artifact = pipeline.run("TEST")
            
            assert artifact is not None
            assert artifact.metrics["auc"] == 0.8
            
            # Verify DataManager called
            mock_data_manager.get_history.assert_called_with("TEST")
            
            # Verify Trainer called
            trainer_instance.train.assert_called_once()
            
            # Verify Save logic (json dump)
            mock_json_dump.assert_called_once()

def test_pipeline_insufficient_data(mock_data_manager):
    # Return empty DF
    mock_data_manager.get_history.return_value = pd.DataFrame()
    
    pipeline = TrainingPipeline(mock_data_manager)
    artifact = pipeline.run("TEST")
    
    assert artifact is None

def test_pipeline_insufficient_aligned_data(mock_data_manager):
    # Return a DF that has data but results in too few samples after alignment
    # e.g. lots of NaNs or very short
    # Here we simulate short history that passes initial check (200) but fails alignment check (100)
    # create_target uses window=5, create_feature_vector consumes ~50 for warmup.
    # If we provide 201 rows? 
    # Alignment drops NaNs.
    
    # Let's simple return data where target becomes all NaNs?
    # Or just return 200 rows with 150 NaNs?
    
    # Easiest: mock prep to return short result?
    # Harder to mock prep since it's instantiated inside.
    
    # Real data approach:
    # 200 rows.
    # Feature warmup: 50.
    # Target window: 5.
    # Valid ~145.
    # We need < 100 valid.
    # So we need warmup to be larger? 
    # FeatureEngine warmup is 50.
    
    # If we return a DF with 110 rows.
    # Initial check might fail? `if df.empty or len(df) < 200:`
    # So we need > 200 input rows.
    
    # If input is 201 rows.
    # We need valid rows < 100.
    # Maybe features return NaN for first 120 rows?
    # Impossible with standard engine unless data is NaN.
    
    # Strategy: Pass data with lots of NaNs in 'close' so technicals are NaN?
    dates = pd.date_range(start="2020-01-01", periods=205, freq="D")
    df = pd.DataFrame({
        "open": 100 + np.random.randn(205),
        "high": 105 + np.random.randn(205),
        "low": 95 + np.random.randn(205),
        "close": 100 + np.random.randn(205),
        "volume": 1000 + np.random.randn(205)
    }, index=dates)
    
    # Inject NaNs to kill feature computation
    # RSI needs 14. If we put NaNs in middle?
    # Let's just mock `create_feature_vector` via patching TrainingDataPrep?
    
    with patch("src.modules.training.pipeline.TrainingDataPrep") as MockPrep:
        prep_instance = MockPrep.return_value
        # Mock features to have 50 rows
        prep_instance.create_feature_vector.return_value = pd.DataFrame(
            {"feat": np.random.randn(50)}, 
            index=dates[:50]
        )
        # Mock target to have 50 rows
        prep_instance.create_target.return_value = pd.Series(
            np.random.randint(0,2,50), 
            index=dates[:50]
        )
        
        pipeline = TrainingPipeline(mock_data_manager)
        
        # We also need to bypass data_manager check?
        # Mock DM returns 'df' with 205 rows (passes >200 check)
        mock_data_manager.get_history.return_value = df
        
        artifact = pipeline.run("TEST")
        
        assert artifact is None
        # Verify print was called? (Optional)

def test_artifact_serialization():
    # Cover ModelArtifact.to_dict
    art = ModelArtifact(
        ticker="TEST",
        model_path="path",
        metrics={"auc": 0.5},
        calibration_curve={},
        feature_names=["a"],
        config=TrainingConfig(max_depth=3)
    )
    d = art.to_dict()
    assert d["ticker"] == "TEST"
    assert d["metrics"]["auc"] == 0.5
    assert d["config"]["max_depth"] == 3
