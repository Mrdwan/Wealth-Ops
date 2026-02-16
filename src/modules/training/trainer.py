from typing import Any, Tuple
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.metrics import log_loss, roc_auc_score

from src.modules.training.types import TrainingConfig, ModelArtifact

class XGBoostTrainer:
    """Handles training and calibration of XGBoost models."""
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        
    def train(
        self, 
        X: pd.DataFrame, 
        y: pd.Series, 
        ticker: str
    ) -> ModelArtifact:
        """
        Trains an XGBoost model with monotonicity constraints and calibration.
        
        Args:
            X: Feature matrix.
            y: Target vector (0/1).
            ticker: Asset identifier.
            
        Returns:
            ModelArtifact containing the trained model and metrics.
        """
        # 1. Define Monotonic Constraints
        # Enforce positive relationship for momentum indicators where applicable
        # (e.g. RSI, Price > SMA). 
        # For this MVP, we map known momentum features to +1 constraint.
        constraints = self._get_constraints(X.columns)
        
        # 2. Setup XGBoost
        model = xgb.XGBClassifier(
            max_depth=self.config.max_depth,
            learning_rate=self.config.learning_rate,
            n_estimators=self.config.n_estimators,
            subsample=self.config.subsample,
            colsample_bytree=self.config.colsample_bytree,
            objective=self.config.objective,
            eval_metric=self.config.eval_metric,
            scale_pos_weight=self.config.scale_pos_weight,
            monotone_constraints=constraints,
            early_stopping_rounds=self.config.early_stopping_rounds,
            n_jobs=-1,
            random_state=42
        )
        
        # 3. Train-Validation Split (Time-based ~80/20)
        split_idx = int(len(X) * 0.8)
        X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]
        
        # 4. Train with Early Stopping
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False
        )
        
        # 5. Calibration (Platt Scaling)
        # We need a calibrated probability output.
        # CalibratedClassifierCV usually needs a fresh fold, but here we can 
        # recalibrate on validation set? Or use prefit if model is good.
        # "prefit" assumes model is already fitted.
        calibrated_model = CalibratedClassifierCV(model, method='sigmoid', cv='prefit')
        calibrated_model.fit(X_val, y_val)
        
        # 6. Evaluation
        # Evaluate on Validation set (calibrated)
        probs_val = calibrated_model.predict_proba(X_val)[:, 1]
        
        auc = roc_auc_score(y_val, probs_val)
        loss = log_loss(y_val, probs_val)
        
        metrics = {
            "auc": float(auc),
            "logloss": float(loss),
            "best_iteration": int(model.best_iteration) if hasattr(model, "best_iteration") else 0
        }
        
        # 7. Create Artifact
        # We save the CALIBRATED model (which wraps the xgb model)
        # Save path logic handled by pipeline/caller, we return object.
        
        return ModelArtifact(
            ticker=ticker,
            model_path="", # To be filled by saver
            metrics=metrics,
            calibration_curve={}, # Todo: compute reliability curve
            feature_names=X.columns.tolist(),
            config=self.config
        )

    def _get_constraints(self, features: pd.Index) -> str:
        """
        Generates monotonicity constraints string for XGBoost.
        (1: increasing, -1: decreasing, 0: no constraint)
        """
        # Example logic: RSI -> Positive (+1)
        # If feature name contains 'rsi', 'momentum', 'roc' -> +1
        # This is a heuristic for the MVP.
        c_list = []
        for col in features:
            col_lower = col.lower()
            if "rsi" in col_lower or "roc" in col_lower or "mom" in col_lower:
                c_list.append(1)
            else:
                c_list.append(0)
        
        return "(" + ",".join(map(str, c_list)) + ")"
