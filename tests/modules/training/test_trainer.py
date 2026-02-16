import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from src.modules.training.trainer import XGBoostTrainer
from src.modules.training.types import TrainingConfig

@pytest.fixture
def mock_data():
    X = pd.DataFrame({
        "rsi": np.random.rand(100),
        "sma": np.random.rand(100)
    })
    y = pd.Series(np.random.randint(0, 2, 100))
    return X, y

def test_trainer_init():
    config = TrainingConfig(max_depth=5)
    trainer = XGBoostTrainer(config)
    assert trainer.config.max_depth == 5

@patch("src.modules.training.trainer.xgb.XGBClassifier")
@patch("src.modules.training.trainer.CalibratedClassifierCV")
def test_train_flow(mock_calib_cls, mock_xgb_cls, mock_data):
    # Setup Mocks
    mock_xgb_instance = MagicMock()
    mock_xgb_cls.return_value = mock_xgb_instance
    
    mock_calib_instance = MagicMock()
    mock_calib_cls.return_value = mock_calib_instance
    
    # Mock predict_proba to return shape (N, 2)
    # len(y_val) approx 20 (20% of 100)
    mock_calib_instance.predict_proba.return_value = np.zeros((20, 2))
    
    X, y = mock_data
    trainer = XGBoostTrainer(TrainingConfig())
    
    artifact = trainer.train(X, y, "TEST")
    
    # Verify XGBoost init with constraints
    mock_xgb_cls.assert_called_once()
    _, kwargs = mock_xgb_cls.call_args
    assert "monotone_constraints" in kwargs
    # RSI should have +1 constraint
    # sma should have 0 (unless we mapped it?)
    # Logic: "rsi" in col -> 1.
    constraints = kwargs["monotone_constraints"]
    assert "(1,0)" in constraints or "(0,1)" in constraints # Order depends on columns
    
    # Verify Fit called
    mock_xgb_instance.fit.assert_called_once()
    
    # Verify Calibration
    mock_calib_cls.assert_called_once()
    mock_calib_instance.fit.assert_called_once()
    
    # Verify Artifact
    assert artifact.ticker == "TEST"
    assert "auc" in artifact.metrics
