# 🗺️ Wealth-Ops v2.0 Roadmap

## ✅ Phase 0: The "Iron" Foundation
- [x] **Step 0.1: Context & Rules.** (Establish the AI Workflow).
- [x] **Step 0.2: Infrastructure as Code.** Setup Terraform/CDK for S3, DynamoDB, ECR, and Step Functions.
- [x] **Step 0.3: CI/CD Pipeline.** GitHub Actions to lint, test, and deploy Lambda/Fargate images.
- [x] **Step 0.4: Local Dev Environment.** Docker Compose with DevContainer + LocalStack (S3/DynamoDB emulation).

## 🟢 Phase 1: The Data Engine & Visibility (Current Focus)
- [x] **Step 1.1: Database Schema.** Define DynamoDB tables for `Config` (Assets to trade), `Ledger` (History), and `Portfolio` (Current State).
- [x] **Step 1.2: Market Data Engine.** (See `specs/data-ingestion-strategy.md`)
  - **Provider Pattern:** Primary: Tiingo (Official) -> Fallback: Yahoo Finance.
  - **Gap-Fill Logic:** Orchestrator Lambda detects and heals missing dates.
  - **Bootstrap (Bulk):** Fargate Task for initial 50-year backfill (to avoid Lambda timeouts).
- [x] **Step 1.3: The Regime Filter (Circuit Breaker).**
  - Logic: If S&P500 < 200-day MA, write `market_status: BEAR` to DynamoDB.
- [x] **Step 1.4: The Daily Briefing (Notifications).**
  - **Tool:** Telegram Bot (Simple Webhook).
  - **Goal:** Receive a daily "Pulse Check" (Market Status + Cash Position) every morning at 09:00.
- [x] **Step 1.5: Lambda Entry Points & Schedulers.**
  - Deploy Lambda handlers for DataManager, RegimeFilter, and TelegramNotifier.
  - CloudWatch Event Rules for daily triggers (23:00 UTC data ingestion, 09:00 UTC pulse).

## 🔴 Phase 2: The Alpha Specialist (Feature Engineering & ML, Multi-Asset)
- [ ] **Step 2.1: Asset Profile Schema.**
  - Add profile fields to `DynamoDB:Config`: `asset_class`, `regime_index`, `regime_direction`, `vix_guard`, `event_guard`, `volume_features`, `benchmark_index`, `concentration_group`.
  - Pre-populate with EQUITY, COMMODITY_HAVEN, COMMODITY_CYCLICAL profiles. See `ARCHITECTURE.md` Section 3.1.
  - FOREX profile defined in schema but **not activated** (placeholder for Phase 5).
- [ ] **Step 2.2: Base Technical Features (11 Features, All Classes).**
  - Implement on **1-Day candles**: RSI (14), EMA_8, EMA_20, EMA_50, MACD Histogram, ADX (14), ATR (14), Upper Wick Ratio, Lower Wick Ratio, EMA Fan, Distance from 20d Low.
  - Edge case: if `(High - Low) == 0`, set both wick ratios to `0.0`.
  - **Profile-agnostic.** These 11 features are computed for every asset regardless of class.
- [ ] **Step 2.3: Class-Specific Features.**
  - **OBV + Volume Ratio:** Computed only when `volume_features = true` in the asset's profile. Applies to EQUITY and COMMODITY (ETF exchange volume). Excluded for FOREX (no centralized volume).
  - **Relative Strength:** `rs_ratio = (Asset_Close / Benchmark_Close)`, normalized to rolling 20-day z-score. Benchmark set by profile: `SPY` for equities, `DXY` for commodities and Forex.
  - **Feature Count:** 14 for EQUITY/COMMODITY, 12 for FOREX.
- [ ] **Step 2.4: Market-Level Data Ingestion (VIX + SPY + DXY).**
  - Add `^VIX` (CBOE Volatility Index), `SPY`, and **`DXY`** (US Dollar Index — via `UUP` ETF proxy or ICE DXY from Yahoo `DX-Y.NYB`) to the data pipeline.
  - **DXY is NEW** — required as regime index for COMMODITY_HAVEN profiles and as RS benchmark for all commodity/Forex models.
  - **Staleness Policy:** If any market-level data (VIX, SPY, DXY) is > 24h stale, corresponding guards default to FAIL. Alert via Telegram.
- [ ] **Step 2.5: Earnings Calendar Integration (EQUITY Only).**
  - Source: Free API (Alpha Vantage earnings calendar or SEC EDGAR).
  - Store `next_earnings_date` per asset in DynamoDB:Config.
  - **Applies only to assets with `event_guard = true`** (EQUITY profile). COMMODITY and FOREX skip this step.
  - **Refresh: Daily** for all EQUITY assets. Companies reschedule with short notice.
- [ ] **Step 2.6: The "One-Asset, One-Model" Pipeline (Profile-Aware).**
  - Fargate Task: Pulls data for Asset X -> Reads profile from DynamoDB:Config -> Computes feature vector per profile -> Trains XGBoost Classifier -> Saves model artifact to S3.
  - **Target:** Predict `High > Close + 3%` within 5 trading days.
  - **Feature Vector:** Determined by profile. 14 features (EQUITY/COMMODITY) or 12 features (FOREX). See `ARCHITECTURE.md` Section 3.2.
  - **Calibration:** Apply **Platt Scaling** post-training. Calibrate and validate **per profile class** — equity models and commodity models are calibrated independently. Validate with reliability diagrams in Phase 2.5.

## 🔴 Phase 2.5: The Proving Ground (Backtesting, Multi-Asset)
- [ ] **Step 2.5.1: The Historical Simulator.**
  - **Task:** Replay the last 1,000 trading days against the trained models.
  - **Profile-Aware:** Simulator reads each asset's profile to apply the correct guards, features, and regime logic. No hard-coded equity assumptions.
  - **Execution Sim:** Simulate the full Trap Order logic:
    - Entry only if next day's High > Signal Candle High + (0.02 × ATR_14) AND < Stop + (0.05 × ATR_14). Gap-throughs = missed signal (no fill).
    - Stop loss executes at market open price if gap-down through stop (simulate slippage, not ideal fill).
    - TP at Entry + (`clamp(2 + ADX_14/30, 2.5, 4.5)` × ATR_14). Chandelier trailing exit at Highest_High - (2 × ATR_14).
  - **Cross-Class Sim:** Test mixed portfolios (e.g., 2 equities + 1 Gold ETF) to validate the diversification benefit of RISK_ON + RISK_OFF positions.
  - **Dual-constraint sizing:** `min(ATR_Size, 15% portfolio cap)`.
  - **Calibration Validation:** Reliability diagrams **per profile class**. If calibration curve deviates > 10% from diagonal at the 0.75 threshold, recalibrate before proceeding.
  - **Goal:** Positive Expectancy > 0.5 **per profile class**.
  - **Gate:** If Backtest fails for any active profile class, do NOT activate that class in Phase 3.

## 🔴 Phase 3: The Judge & Execution (Gray Box, Multi-Asset)
- [ ] **Step 3.1: Profile-Aware Hard Guards Lambda.**
  - Reads each asset's profile from DynamoDB:Config. Evaluates **only applicable** guards. See `ARCHITECTURE.md` Section 4.B.
  - **Guard 1 (Macro Gate):** Conditional on `regime_direction`:
    - EQUITY: `SPY_Close > SMA(SPY, 200)`. Source: DynamoDB (Phase 1.3).
    - COMMODITY_HAVEN: `DXY_Close < SMA(DXY, 200)` (inverted). Source: S3 (Phase 2.4).
    - COMMODITY_CYCLICAL: `SPY_Close > SMA(SPY, 200)`. Same as equity.
    - FOREX: **Skipped** (`regime_direction = ANY`).
  - **Guard 2 (Panic Guard):** `VIX_Close < 30`. Only evaluated if `vix_guard = true` (EQUITY + COMMODITY_CYCLICAL). Source: S3 (Phase 2.4).
  - **Guard 3 (Exposure Cap):** `count(open_positions) < 4`. Always. Cross-class total. Source: DynamoDB:Portfolio.
  - **Guard 4 (Trend Gate):** `ADX_14 > 20` per asset. Always.
  - **Guard 5 (Event Guard):** `Days_to_Earnings >= 7`. Only if `event_guard = true` (EQUITY only). Source: DynamoDB:Config (Phase 2.5). **Refreshed daily.**
  - **Guard 6 (Pullback Zone):** `(Close - EMA_8) / EMA_8 <= 0.05` per asset. Always. One-sided (upside only).
  - **Data Staleness:** If S&P, VIX, or DXY data is stale > 24h, corresponding guard defaults to FAIL. Telegram alert fires.
- [ ] **Step 3.2: Soft Gate (ML Scoring).**
  - Load calibrated XGBoost model from S3 for each asset that passed all applicable Hard Guards.
  - Model was trained with the asset's profile feature vector (14 or 12 features).
  - **Rule:** `XGBoost_Calibrated_Probability > 0.75`.
- [ ] **Step 3.3: Portfolio Guard.**
  - **Concentration Limit:** Max 1 position per group. EQUITY: sector. COMMODITY: commodity type. FOREX: currency family. Highest probability wins ties.
  - **Position Cap:** `Position_Value <= 15% of Portfolio`. Dual-constraint with ATR sizing. See `ARCHITECTURE.md` Section 4.D.
  - **News Veto (LLM):** DeepSeek-V3 or Gemini Flash API. Triggered for all asset classes if a BUY signal survives all prior gates. See `specs/ml-compute-strategy.md`.
- [ ] **Step 3.4: Trap Order Execution Engine.**
  - **Entry:** BUY STOP LIMIT at `High_of_Signal_Candle + (0.02 × ATR_14)`, limit at `Stop + (0.05 × ATR_14)`.
  - **Gap-Through Policy:** If asset opens above Limit Price, order does not fill. Accepted by design. See `ARCHITECTURE.md` Section 4.E.
  - **TTL:** 1 trading session (EQUITY/COMMODITY). 24 clock hours (FOREX, future).
  - **Position Sizing:** `min((Portfolio × 0.02) / (ATR_14 × 2), Portfolio × 0.15 / Entry_Price)`.
  - **Exit Rules:**
    - TP: Sell 50% at `Entry + (clamp(2 + ADX_14/30, 2.5, 4.5) × ATR_14)`. ADX-scaled. All classes.
    - Trail: Chandelier Stop on remainder at `Highest_High_Since_Entry - (2 × ATR_14)`. All classes.
    - Stop Loss: **Market order** at `Entry - (2 × ATR_14)`. Guarantees fill through gaps. All classes.
    - Time Stop: Close at market after 10 trading days. All classes.
  - **Phase:** Mock Paper Trading with multi-asset portfolio (equities + commodities), then IBKR integration.

## 🔴 Phase 4: The Dashboard & Polish
- [ ] **Step 4.1: Static Dashboard.** Streamlit or React page showing Portfolio Performance, **grouped by asset class** (Equity, Commodity, Forex).
- [ ] **Step 4.2: Modular Asset Config.** Script to add/remove tickers **with profile assignment** (EQUITY, COMMODITY_HAVEN, COMMODITY_CYCLICAL). Validates that required data feeds (SPY, VIX, DXY) are active for the selected profile.

## 🔴 Phase 5: Forex Support (Architecture Ready, Implementation Pending)
> The profile system (Section 3.1) and guard framework (Section 4.B) already support FOREX as a slot. This phase activates it.

- [ ] **Step 5.1: Forex Data Provider.**
  - Evaluate Forex data sources (Tiingo Forex API, OANDA, or equivalent).
  - Ingest daily Forex bars (24h session close, 5 days/week).
- [ ] **Step 5.2: 12-Feature Model Training.**
  - Train XGBoost models using the 12-feature vector (no OBV, no Volume Ratio).
  - RS ratio benchmarked against DXY.
  - Calibrate independently from equity/commodity models.
- [ ] **Step 5.3: Forex-Specific Execution Adjustments.**
  - TTL: 24 clock hours instead of trading session.
  - Gap-Through Policy: Rarely triggers (24h market). Keep as weekend gap safety net.
  - Position Cap: Evaluate whether 15% can be relaxed (lower overnight gap risk).
- [ ] **Step 5.4: Economic Calendar Guard (Forex Hard Guard).**
  - Central bank decision dates (FOMC, ECB, BoE) and major releases (NFP, CPI).
  - Equivalent of the Event Guard but for Forex. `Days_to_Central_Bank_Decision >= 3`.
  - Source: Free economic calendar API.
