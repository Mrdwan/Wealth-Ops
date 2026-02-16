from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any

@dataclass
class TrainingConfig:
    """Configuration for XGBoost training."""
    max_depth: int = 4
    learning_rate: float = 0.05
    n_estimators: int = 500
    early_stopping_rounds: int = 50
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    objective: str = "binary:logistic"
    eval_metric: str = "logloss"
    scale_pos_weight: float = 1.0  # Balance handling
    
    # Target definition
    target_window: int = 5         # Look ahead 5 days
    target_threshold: float = 0.03 # 3% gain

@dataclass
class ModelArtifact:
    """Represents a trained model artifact to be saved/loaded."""
    ticker: str
    model_path: str                # Local or S3 path
    metrics: dict[str, float]      # AUC, LogLoss, Precision, Recall
    calibration_curve: dict[str, list[float]] # For plotting/validation
    feature_names: list[str]       # To ensure correct inference order
    training_date: datetime = field(default_factory=datetime.utcnow)
    config: TrainingConfig = field(default_factory=TrainingConfig)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize/dictify for metadata storage."""
        return {
            "ticker": self.ticker,
            "metrics": self.metrics,
            "training_date": self.training_date.isoformat(),
            "config": self.config.__dict__
        }
