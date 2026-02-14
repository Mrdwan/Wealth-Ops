# 🗺️ Wealth-Ops v3.0 Roadmap

## ✅ Phase 0: The "Iron" Foundation (Carried from v2.0)
- [x] **Step 0.1: Context & Rules.** AI Workflow established. Constitution documented.
- [x] **Step 0.2: Infrastructure as Code.** CDK for S3, DynamoDB, ECR, Step Functions.
- [x] **Step 0.3: CI/CD Pipeline.** GitHub Actions to lint, test, and deploy Lambda/Fargate images.
- [x] **Step 0.4: Local Dev Environment.** Docker Compose with DevContainer + LocalStack.

## ✅ Phase 1: The Data Engine & Visibility (Carried from v2.0, Enhanced)
- [x] **Step 1.1: Database Schema.** DynamoDB tables for Config, Ledger, Portfolio.
- [x] **Step 1.2: Market Data Engine (Tiingo Primary).**
  - Provider Pattern: Primary: Tiingo → Fallback: Yahoo Finance (stocks).
  - Gap-Fill Logic: Orchestrator Lambda detects and heals missing dates.
  - Bootstrap: Fargate Task for initial 10-year backfill.
- [x] **Step 1.3: The Regime Filter (Circuit Breaker).**
  - SPY < 200-day MA → `market_status: BEAR` in DynamoDB.
- [x] **Step 1.4: The Daily Briefing (Telegram, One-Way).**
  - Telegram Bot webhook. Daily "Pulse Check" at 09:00 UTC.
- [x] **Step 1.5: Lambda Entry Points & Schedulers.**
  - Handlers for DataManager, RegimeFilter, TelegramNotifier.
  - CloudWatch Events: 23:00 UTC data ingest, 09:00 UTC pulse.

### ← v3.0 ADDITIONS TO PHASE 1 →

- [x] **Step 1.6: Tiingo Forex Integration (Gold/Silver).** ← NEW
  - `TiingoForexProvider` class for XAU/USD, XAG/USD via Tiingo Forex API.
  - Daily OHLC bars (volume=0 for forex). Cross-reference with GLD ETF price (>2% divergence = alert).
  - Store in `s3://wealth-ops-data/ohlcv/forex/XAUUSD/daily/`.

- [x] **Step 1.7: FRED Macro Data Pipeline.** ← NEW
  - `MacroDataProvider` protocol + `FredProvider` class + `MacroDataManager` orchestrator.
  - Ingest: VIX (`VIXCLS`), Yield Curve (`T10Y2Y`), Fed Funds (`FEDFUNDS`), CPI (`CPIAUCSL`).
  - Store in `s3://wealth-ops-data/ohlcv/macro/`.
  - Per-series staleness: daily=24h, monthly=35d. Stale → guards default to FAIL.

- [x] **Step 1.8: DXY Index Data.** ← NEW
  - Source: Tiingo (UUP ETF proxy). Uses existing `TiingoProvider`.
  - Store in `s3://wealth-ops-data/ohlcv/indices/UUP/daily/`.

- [x] **Step 1.9: Asset Profile Schema v3.** ← NEW
  - `AssetProfile` frozen dataclass with `from_dynamodb_item()` + `to_dynamodb_item()` + `s3_prefix()`.
  - Pre-built templates: EQUITY, COMMODITY_HAVEN, COMMODITY_CYCLICAL, INDEX.
  - Profile-aware data ingestion: routes tickers to correct provider + S3 path.
  - Seed script: `scripts/seed_profiles.py`.

- [x] **Step 1.10: Two-Way Telegram Commands.** ← NEW
  - Lambda Function URL webhook handler with command routing.
  - Commands: `/status`, `/portfolio`, `/risk`, `/help`.
  - Chat ID security validation. `send_reply()` method on TelegramNotifier.
  - Signal execution commands (`/executed`, `/skip`, `/close`) added in Phase 3.

---

## 🟢 Phase 2A: Momentum Composite (NEW — Academic Baseline)
> **Goal:** Deploy the academically-backed momentum signal FIRST as the baseline. This runs before XGBoost and provides a signal even without ML.

- [x] **Step 2A.1: Base Technical Feature Engine.**
  - `FeatureEngine` class with 11 base indicators: RSI(14), EMA_8/20/50, MACD Histogram, ADX(14), ATR(14), Upper/Lower Wick Ratios, EMA Fan, Distance from 20d Low.
  - Edge case: `(High - Low) == 0` → both wick ratios = `0.0`.
  - Profile-agnostic: 11 features computed for every asset.

- [x] **Step 2A.2: Class-Specific Features.**
  - OBV + Volume Ratio: only when `volume_features = true` (EQUITY).
  - Relative Strength: z-scored `asset_close / benchmark_close` ratio. Benchmark per profile (SPY for equities, UUP for commodities).
  - Feature count: 14 (EQUITY), 12 (COMMODITY_HAVEN/FOREX).

- [x] **Step 2A.3: Momentum Composite Score.**
  - Implement 6-component composite: Momentum (40%), Trend (20%), RSI (15%), Volume (10%), ATR Volatility (10%), Support/Resistance (5%).
  - All components z-score normalized before weighting.
  - Volume component skipped for `volume_features = false` assets, weights redistribute.
  - Thresholds: STRONG_BUY >2.0σ, BUY >1.5σ, NEUTRAL ±1.5σ, SELL <-1.5σ.

- [x] **Step 2A.4: Momentum Signal Cards.**
  - Telegram signal delivery with entry zones, stop loss, TP, position size, reasoning.
  - Cards include composite score breakdown (which components contribute most).
  - Trap Order parameters calculated and included.

- [x] **Step 2A.5: Market-Level Data Integration.**
  - VIX, SPY, DXY data flowing into signal pipeline.
  - Staleness policy enforced: >24h stale → guard defaults to FAIL, Telegram alert.

---

## 🔴 Phase 2B: The XGBoost Alpha Specialist (Evolved from v2 Phase 2)
> **Goal:** Add XGBoost per-asset models ON TOP of the momentum baseline. Compare their performance independently.

- [ ] **Step 2B.1: Earnings Calendar Integration (EQUITY Only).**
  - Source: Tiingo Fundamentals or Alpha Vantage earnings calendar.
  - Store `next_earnings_date` per equity asset. Refresh daily.
  - Only for assets with `event_guard = true`.

- [ ] **Step 2B.2: Economic Calendar Integration (COMMODITY/FOREX).** ← NEW
  - Source: FRED + Finnhub free API.
  - Track FOMC meeting dates, NFP release dates, CPI releases.
  - Store `next_macro_event_date` for `macro_event_guard = true` assets.
  - Guard: `Days_to_FOMC/NFP >= 2`.

- [ ] **Step 2B.3: The "One-Asset, One-Model" Pipeline.**
  - Fargate Task: Pull data → Read profile → Compute feature vector → Train XGBoost → Save to S3.
  - Target: `High > Close + 3%` within 5 trading days.
  - Feature vector: determined by profile (14 or 12 features).
  - Calibration: Platt Scaling post-training. Validate per profile class.

- [ ] **Step 2B.4: Dual Signal Comparison.**
  - Run Momentum Composite AND XGBoost in parallel.
  - Log both scores for every asset every day (even when no signal fires).
  - Signal cards show both: "Momentum: 1.9σ | XGBoost: 82%".
  - See ARCHITECTURE.md Section 7 for agreement matrix.

---

## 🔴 Phase 2.5: The Proving Ground (Backtesting, Enhanced for v3)

- [ ] **Step 2.5.1: Walk-Forward Optimization.** ← NEW
  - Training window: 3 years (expanding). Test window: 6 months. Roll forward 6 months.
  - Minimum 10 walk-forward periods (requires 5+ years of data).
  - Walk-Forward Efficiency > 50% required.

- [ ] **Step 2.5.2: Execution-Realistic Simulator (From v2).**
  - Full Trap Order logic: entry only if next day's High > Signal Candle High + (0.02 × ATR_14).
  - Gap-throughs = missed signal. Stop loss at market open on gap-down (slippage sim).
  - Dual-constraint sizing: `min(ATR_Size, 15% portfolio cap)`.
  - **Profile-Aware:** Reads each asset's profile for correct guards, features, regime logic.

- [ ] **Step 2.5.3: Monte Carlo Validation.** ← NEW
  - 10,000 bootstrap iterations of trade returns.
  - 5th percentile of terminal wealth must be positive.
  - Shuffled-price test: strategy must fail on randomly permuted returns (p < 0.01).

- [ ] **Step 2.5.4: Overfitting Detection.** ← NEW
  - t-statistic > 2.0 required for signal significance.
  - Red flags: Sharpe > 3.0, Profit Factor > 2.5, Max DD < 5%, Win Rate > 75%.
  - If any red flag triggers: review, do not deploy.

- [ ] **Step 2.5.5: Calibration Validation.**
  - Reliability diagrams per profile class.
  - If calibration curve deviates >10% from diagonal at 0.75 threshold → recalibrate.

- [ ] **Step 2.5.6: Cross-Class Portfolio Sim.**
  - Test mixed portfolios: 2 equities + 1 Gold (XAU/USD).
  - Validate diversification benefit of RISK_ON + RISK_OFF positions.
  - Run with both Momentum-only AND Momentum+XGBoost to measure ML's marginal contribution.

- [ ] **Step 2.5.7: Paper Trading Gate.**
  - Minimum 3 months, minimum 30 trades.
  - Live results within 1σ of backtest.
  - Slippage < 0.3%. Miss rate < 20%.
  - **Gate:** If backtest fails for any active profile class, do NOT activate that class in Phase 3.

---

## 🔴 Phase 3: The Judge & Execution (Enhanced for v3)

- [ ] **Step 3.1: Profile-Aware Hard Guards Lambda.**
  - 8 guards (v3 adds Macro Event Guard and Drawdown Gate). See ARCHITECTURE.md Section 8.B.
  - Guard 1 (Macro Gate): Conditional on `regime_direction`. SPY/DXY/ANY.
  - Guard 2 (Panic Guard): `VIX < 30`. Only if `vix_guard = true`.
  - Guard 3 (Exposure Cap): `count(open_positions) < max_positions`. Always.
  - Guard 4 (Trend Gate): `ADX_14 > 20`. Always.
  - Guard 5 (Event Guard): `Days_to_Earnings >= 7`. Only `event_guard = true`.
  - Guard 6 (Macro Event Guard): `Days_to_FOMC/NFP >= 2`. Only `macro_event_guard = true`. ← NEW
  - Guard 7 (Pullback Zone): `(Close - EMA_8) / EMA_8 <= 0.05`. Always.
  - Guard 8 (Drawdown Gate): Dynamic throttling per ARCHITECTURE.md Section 9. ← NEW

- [ ] **Step 3.2: Soft Gate (ML Scoring).**
  - Load calibrated XGBoost model from S3.
  - Rule: `XGBoost_Calibrated_Probability > 0.75`.
  - Also log Momentum Composite score for comparison.

- [ ] **Step 3.3: Portfolio Guard.**
  - Concentration Limit: Max 1 per group. Highest probability wins.
  - Position Cap: `min(ATR_Size, Portfolio × 0.15 / Entry_Price)`.
  - **Correlation Check (NEW):** Rolling 60-day correlation. No new position if >0.70 correlated with existing.
  - News Veto (LLM): DeepSeek-V3 or Gemini Flash.

- [ ] **Step 3.4: Dynamic Risk Management.** ← NEW
  - Portfolio state tracking in DynamoDB (cash, equity, peak, drawdown, risk_status).
  - Drawdown throttling: 8% → half sizes, 12% → 1 position max, 15% → HALT.
  - Capital-based scaling: <€5K = 3 positions/1%, €5-15K = 4/1.5%, €15K+ = 5/2%.
  - Cash reserve minimum enforced (40% at <€5K, 30% at €5-15K, 25% at €15K+).

- [ ] **Step 3.5: Trap Order Execution Engine.**
  - Entry: BUY STOP LIMIT at `High + (0.02 × ATR_14)`.
  - Gap-Through Policy: no fill if opens above limit. By design.
  - ADX-scaled TP: `clamp(2 + ADX/30, 2.5, 4.5) × ATR_14`.
  - Chandelier trailing stop. Market order stop loss. 10-day time stop.
  - Phase: Paper trading first, then IBKR + IG integration.

- [ ] **Step 3.6: Full Telegram Command Interface.** ← NEW
  - `/executed <id> [price]`, `/skip <id>`, `/close <id> [price]`.
  - `/pause`, `/resume`, `/performance`.
  - Position alerts: stop proximity, trailing updates, TP hits, regime changes.
  - Signal cards per ARCHITECTURE.md Section 12.1.

- [ ] **Step 3.7: Broker Abstraction Layer.** ← NEW
  - `BrokerInterface` ABC with `IGBroker`, `IBKRBroker`, `PaperBroker` implementations.
  - Phase 3: PaperBroker only (simulated execution).
  - Broker field in asset profile routes each asset to correct broker.
  - Tax rate field for P&L reporting.

---

## 🔴 Phase 4: ML Regime Classifier (NEW in v3)
> **Goal:** Add a LightGBM regime classifier that adjusts Hard Guard parameters and position sizing. Does NOT generate signals.

- [ ] **Step 4.1: Regime Feature Engineering.**
  - 15 features: Momentum (4 periods), RSI, MACD histogram, Bollinger %B, vol ratios, volume ratios, VIX level, VIX change, yield curve, fed funds rate, DXY momentum.
  - All from existing data pipeline (no new sources needed).

- [ ] **Step 4.2: LightGBM Training.**
  - Target: next 20-day return direction (binary).
  - Training: expanding window, retrain monthly.
  - Expected accuracy: 52–56%.
  - Runs on Lambda (3GB ARM). LightGBM trains in seconds on daily data.

- [ ] **Step 4.3: Regime Integration.**
  - 5 regimes: BULL_TREND, BEAR_TREND, HIGH_VOLATILITY, LOW_VOLATILITY, TRANSITION.
  - Regime adjusts: position sizes, stop-loss tightness, TP targets.
  - Existing Macro Gate (SPY > 200 SMA) remains as fallback.

- [ ] **Step 4.4: Regime Validation.**
  - Backtest with vs. without regime classifier.
  - **Deploy ONLY if measurable improvement** over no regime filter.
  - Regime displayed in daily briefing and signal cards.

---

## 🔴 Phase 5: Live Trading (Enhanced for v3)

- [ ] **Step 5.1: Paper Trading Analysis.**
  - Minimum 3 months, 30 trades analyzed.
  - Check: positive expectancy, Sharpe >0.5, max DD <15%.
  - Live vs backtest within 1σ.
  - Kill conditions checked (see ARCHITECTURE.md Section 13).

- [ ] **Step 5.2: Broker Account Setup.**
  - **IG Ireland:** Fund account (minimum €300). Verify spread betting API access.
  - **IBKR Ireland (IBIE):** Fund account. Activate IBKR Pro for API.
  - Test API connectivity from Lambda for both.

- [ ] **Step 5.3: Live Gold (IG First).**
  - Start with XAU/USD only on IG spread betting.
  - **HALF of backtested position sizes** for first month.
  - Monitor: slippage, spread costs, overnight funding charges.
  - Tax: track that IG profits are tax-free (spread betting exemption).

- [ ] **Step 5.4: Live Stocks (IBKR Second).**
  - Add US equity trades via IBKR after 1+ month on IG.
  - HALF sizes for first month.
  - Tax: track 33% CGT, €1,270 annual exemption.

- [ ] **Step 5.5: Full Portfolio.**
  - Mixed portfolio: equities (IBKR) + commodities (IG).
  - Validate cross-asset correlation and diversification benefit.
  - Scale to full position sizes only after 2+ months of live results.

---

## 🔴 Phase 6: Dashboard & Polish

- [ ] **Step 6.1: Static Dashboard.**
  - Streamlit or React page showing Portfolio Performance grouped by asset class.
  - Equity curve, drawdown chart, trade log, regime timeline.

- [ ] **Step 6.2: Modular Asset Config.**
  - Script to add/remove tickers with profile assignment.
  - Validates required data feeds are active for selected profile.

---

## 🔴 Phase 7: Forex Support (Architecture Ready, Not Activated)
> Profile system and guard framework already support FOREX as a slot. This phase activates it.

- [ ] **Step 7.1: Forex Data Provider.** Tiingo Forex for daily bars (already integrated for XAU/USD).
- [ ] **Step 7.2: 12-Feature Model Training.** No OBV/Volume Ratio. RS vs DXY.
- [ ] **Step 7.3: Forex Execution Adjustments.** TTL: 24 clock hours. Gap-through rare.
- [ ] **Step 7.4: Economic Calendar Guard.** Central bank decisions >= 3 days out.

---

## Timeline Estimate (Solo Dev, ~1hr/day + weekends)

| Phase | Duration | Cumulative | Deliverable |
|-------|----------|-----------|-------------|
| 1 (remaining) | 2 weeks | Week 2 | Tiingo Forex + FRED data flowing, two-way Telegram |
| 2A | 3 weeks | Week 5 | Momentum signals live, paper trading begins |
| 2B | 3 weeks | Week 8 | XGBoost models trained, dual-signal comparison |
| 2.5 | 3 weeks | Week 11 | Backtesting validated (walk-forward + Monte Carlo) |
| 3 | 4 weeks | Week 15 | Full pipeline: signal → guards → risk → notify |
| 4 | 3 weeks | Week 18 | Regime classifier (deploy only if proven) |
| 5 | 3+ months | Month 7+ | Paper trading complete, live with HALF sizes |

**Key gates:** Phase 2.5 can BLOCK Phase 3 activation for failing profile classes. Phase 5.1 can BLOCK live trading if paper results diverge.

---

*Wealth-Ops v3.0 Roadmap — February 2026*
