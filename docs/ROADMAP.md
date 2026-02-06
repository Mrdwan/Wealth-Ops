# 🗺️ Wealth-Ops v2.0 Roadmap

## 🟢 Phase 0: The "Iron" Foundation (Current Focus)
- [ ] **Step 0.1: Context & Rules.** (Establish the AI Workflow).
- [ ] **Step 0.2: Infrastructure as Code.** Setup Terraform/CDK for S3, DynamoDB, ECR, and Step Functions.
- [ ] **Step 0.3: CI/CD Pipeline.** GitHub Actions to lint, test, and deploy Lambda/Fargate images.

## 🟡 Phase 1: The Data Engine & Visibility
- [ ] **Step 1.1: Database Schema.** Define DynamoDB tables for `Config` (Assets to trade), `Ledger` (History), and `Portfolio` (Current State).
- [ ] **Step 1.2: Market Data Ingest.** Lambda to fetch Daily Candles -> S3 Parquet.
  - **Bootstrap (One-time):** Tiingo Free Tier (50+ years historical backfill).
  - **Daily Drip:** Yahoo Finance (ongoing updates, $0/month).
  - **Rebuild (Optional):** Tiingo Paid ($30) if data needs refresh.
- [ ] **Step 1.3: The Regime Filter (Circuit Breaker).**
  - Logic: If S&P500 < 200-day MA, write `market_status: BEAR` to DynamoDB.
- [ ] **Step 1.4: The Daily Briefing (Notifications).**
  - **Tool:** Telegram Bot (Simple Webhook).
  - **Goal:** Receive a daily "Pulse Check" (Market Status + Cash Position) every morning at 09:00.

## 🔴 Phase 2: The Alpha Specialist (Machine Learning)
- [ ] **Step 2.1: Feature Engineering.** Implement RSI, EMA, MACD, **ADX** (Volatility), **OBV** (Volume), and **ATR** (Stop Loss Calc) on **1-Day** candles.
- [ ] **Step 2.2: The "One-Asset, One-Model" Pipeline.**
  - Fargate Task: Pulls data for Asset X -> Trains XGBoost -> Saves Model to S3.
  - **Target:** Predict "High > Close + 3% within 5 Days".

## 🔴 Phase 2.5: The Proving Ground (Backtesting)
- [ ] **Step 2.5.1: The Historical Simulator.**
  - **Task:** Replay the last 1,000 days of data against the trained models.
  - **Goal:** Verify that the "75% Confidence" threshold yields positive Expectancy > 0.5.
  - **Gate:** If Backtest fails, do NOT proceed to Phase 3.

## 🔴 Phase 3: The Judge & Execution
- [ ] **Step 3.1: The Judge Lambda.**
  - **Gate 1:** Reads `market_status` (Phase 1.3).
  - **Gate 2:** Checks ADX < 20 (Phase 2.1).
  - **Gate 3:** Reads XGBoost Score > 75% (Phase 2.2).
  - **Gate 4:** Applies **Sector Correlation Limit** (Max 1 per Sector).
  - **Gate 5:** Calls LLM (News Veto).
- [ ] **Step 3.2: Execution Engine.** Mock Paper Trading first, then API integration.

## 🔴 Phase 4: The Dashboard & Polish
- [ ] **Step 4.1: Static Dashboard.** A simple Streamlit or React page reading from DynamoDB to show Portfolio Performance.
- [ ] **Step 4.2: Modular Asset Config.** A script to easily add/remove tickers from the `Config` table.