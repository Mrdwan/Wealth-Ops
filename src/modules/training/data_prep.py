from typing import Tuple, Optional
import pandas as pd
import numpy as np
from src.modules.features.engine import FeatureEngine
from src.shared.profiles import AssetProfile

class TrainingDataPrep:
    """Prepares feature vectors and target labels for XGBoost training."""
    
    def __init__(self, feature_engine: Optional[FeatureEngine] = None):
        self.feature_engine = feature_engine or FeatureEngine()

    def create_feature_vector(self, df: pd.DataFrame, profile: AssetProfile) -> pd.DataFrame:
        """
        Generates the standard feature vector for a given asset.
        
        Args:
            df: OHLCV DataFrame (must have DatetimeIndex).
            profile: AssetProfile to determine specific feature set (e.g. Volume).
            
        Returns:
            DataFrame with computed features, aligned with input index.
        """
        if df.empty:
            return pd.DataFrame()

        # 1. Compute Base Technicals (RSI, MACD, etc)
        # Using feature engine which returns a rich dataframe
        # Pass volume_features from profile to handle filtering at source
        features = self.feature_engine.compute(
            df, 
            volume_features=profile.volume_features
        )
        
        # 2. Filter/Select features based on Profile
        # FeatureEngine.compute already handles volume_features flag, 
        # so manual dropping is redundant if we pass the flag.
            
        # 3. Add Numeric Context Features (Regime)
        # For now, we assume Regime is passed in or we compute simple derived features here
        # (e.g. distance from SMA200)
        # TODO: Integrate with Regime/MarketContext module properly if needed.
        # For this step, we stick to technicals + maybe day-of-week.
        
        features["day_of_week"] = features.index.dayofweek
        features["month"] = features.index.month
        
        return features.dropna()

    def create_target(
        self, 
        df: pd.DataFrame, 
        window: int = 5, 
        threshold: float = 0.03
    ) -> pd.Series:
        """
        Generates the target label: 1 if Max High (t+1..t+window) >= Close(t) * (1 + threshold).
        
        Args:
            df: OHLCV DataFrame
            window: Lookahead window in days
            threshold: Required percentage gain (e.g. 0.03 for 3%)
            
        Returns:
            Boolean Series (1/0) aligned with df index. Last 'window' rows will be NaN.
        """
        # Calculate Rolling Max High shifted backward
        # shift(-1) moves t+1 to t.
        # rolling(window).max() looks back.
        # So: df["high"].shift(-1).rolling(window).max()
        # No, rolling is look-back. 
        # Correct approach: Inverse rolling or shift logic.
        
        # We want at time t: Max(High[t+1] ... High[t+window])
        # This is equivalent to: reverse df, rolling max, reverse back?
        # Or: Use fixed forward window indexer.
        
        # Easiest pandas vectorization:
        indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=window)
        rolling_max_future = df["high"].shift(-1).rolling(window=indexer).max()
        
        # Determine Breakout
        # Target Price = Close[t] * (1 + threshold)
        required_price = df["close"] * (1.0 + threshold)
        
        # If Future High >= Required Price -> 1, else 0
        target = (rolling_max_future >= required_price).astype(int)
        
        # The last 'window' rows are invalid because they don't have enough future data
        # FixedForwardWindowIndexer might handle this, but let's be safe.
        # Actually shift(-1) makes the last row NaN.
        # We should mask the last `window` rows as NaN to avoid training on partial data.
        target.iloc[-window:] = np.nan
        
        return target
