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
  - **Gate 5:** Calls LLM (News Veto). **See `specs/ml-compute-strategy.md`** (DeepSeek/Gemini API, no FinBERT).
- [ ] **Step 3.2: Execution Engine.** Mock Paper Trading first, then API integration.

## 🔴 Phase 4: The Dashboard & Polish
- [ ] **Step 4.1: Static Dashboard.** A simple Streamlit or React page reading from DynamoDB to show Portfolio Performance.
- [ ] **Step 4.2: Modular Asset Config.** A script to easily add/remove tickers from the `Config` table.