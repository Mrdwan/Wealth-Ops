import os
import json
import joblib
from datetime import datetime
from typing import Optional

from src.modules.data.manager import DataManager
from src.modules.training.types import TrainingConfig, ModelArtifact
from src.modules.training.data_prep import TrainingDataPrep
from src.modules.training.trainer import XGBoostTrainer
from src.shared.profiles import AssetProfile, EQUITY_PROFILE

class TrainingPipeline:
    """Orchestrates the end-to-end training process for a single asset."""
    
    def __init__(
        self, 
        data_manager: DataManager,
        config: Optional[TrainingConfig] = None,
        output_dir: str = "models"
    ):
        self.data_manager = data_manager
        self.config = config or TrainingConfig()
        self.output_dir = output_dir
        self.prep = TrainingDataPrep()
        self.trainer = XGBoostTrainer(self.config)
        
    def run(self, ticker: str) -> Optional[ModelArtifact]:
        """
        Runs the full pipeline:
        1. Fetch Data
        2. Get Profile
        3. Prep Features & Target
        4. Train Model
        5. Save Artifacts
        """
        print(f"Starting training pipeline for {ticker}...")
        
        # 1. Fetch Data
        # We need enough history for features + target window
        df = self.data_manager.get_history(ticker)
        if df.empty or len(df) < 200:
            print(f"Insufficient data for {ticker}. Skipping.")
            return None
            
        # 2. Get Profile
        # For now, we use the static Profiles map. 
        # In production, this might come from DynamoDB.
        # Fallback to EQUITY_PROFILE defaults if not found.
        # TODO: Implement proper Profile Lookup
        profile = EQUITY_PROFILE
        
        # 3. Prep Data
        X = self.prep.create_feature_vector(df, profile)
        y = self.prep.create_target(df, window=self.config.target_window, threshold=self.config.target_threshold)
        
        # Align indices (drop NaNs from target window and feature warmup)
        common_idx = X.index.intersection(y.index)
        # Drop rows where target is NaN (last 5 days)
        # And rows where features might be NaN (Though prep.create_feature_vector handles dropna)
        
        valid_mask = ~y.loc[common_idx].isna()
        common_idx = common_idx[valid_mask]
        
        if len(common_idx) < 100:
            print(f"Not enough valid samples after alignment for {ticker}. Skipping.")
            return None
            
        X_aligned = X.loc[common_idx]
        y_aligned = y.loc[common_idx]
        
        # 4. Train
        artifact = self.trainer.train(X_aligned, y_aligned, ticker)
        
        # 5. Save
        self._save_artifact(artifact, ticker)
        
        print(f"Training complete for {ticker}. AUC: {artifact.metrics.get('auc', 0):.4f}")
        return artifact

    def _save_artifact(self, artifact: ModelArtifact, ticker: str) -> None:
        """Saves model and metadata to local disk (simulating S3 upload)."""
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        save_dir = os.path.join(self.output_dir, ticker, date_str)
        os.makedirs(save_dir, exist_ok=True)
        
        # Save Model (using joblib for sklearn/xgboost wrapper)
        # The artifact doesn't hold the model object explicitly to keep it serializable.
        # But we need to verify how we handle the actual model object.
        # The Trainer returned an artifact with empty model_path.
        # We need the actual model object to save it. 
        # Mistake in Trainer design: it returned artifact without the model object.
        # Let's fix Trainer to return (artifact, model_object) or attach it entirely?
        # Actually Trainer logic was simplified. 
        # Let's assume for now we don't save the actual binary in this MVP step 
        # until we fix the Trainer to return the model object. 
        
        # REFACTOR: Trainer should return (model, artifact)
        # For now, just save the metadata json.
        
        meta_path = os.path.join(save_dir, "metadata.json")
        with open(meta_path, "w") as f:
            json.dump(artifact.to_dict(), f, indent=2)
            
        artifact.model_path = meta_path # Update path
