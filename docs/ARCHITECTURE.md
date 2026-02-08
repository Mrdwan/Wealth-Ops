# 🏛️ Wealth-Ops v2.0 Architecture

## 1. Core Philosophy
A cloud-native, automated trading system for a **Solo Trader (Irish Tax Resident)**.
- **Strategy:** "The Swing Sniper" (Daily Candles, 3-10 day hold).
- **Tax Logic:** Minimize ETFs (41% Tax). Prioritize Individual Stocks (33% CGT).
- **Quality:** 100% Test Coverage required for all financial logic.
- **Hybrid AI Model:** "Hard Guards, Soft Skills." We enforce Risk Rules (Hard), AI learns Entry Patterns (Soft).

## 2. The Cloud Stack (AWS)
- **Ingest & Scout:** AWS Lambda (Daily Drip via CloudWatch Events) & Fargate (Bulk Bootstrap). Features "Smart Gap-Fill".
- **The Specialist (Training):** AWS Fargate (ECS). Spins up, trains XGBoost models for each asset.
- **The Judge & Execution:** AWS Lambda. Reads S3 models, predicts, calls LLM API, executes trade.
- **State Store:** AWS DynamoDB (Ledger, Holdings, Config).
- **Data Lake:** AWS S3 (Parquet History, Model Artifacts).
- **Orchestration:** AWS Step Functions (Visual Workflow).
- **Data Sources:** (See `specs/data-ingestion-strategy.md`)
    - **Primary:** Tiingo (Official API).
    - **Fallback:** Yahoo Finance (yfinance).
    - **Resiliency:** Auto-failover and gap detection.

## 2.5 Local Development (Docker Compose)
All AWS services are emulated locally via **LocalStack** for development and testing.

| Service | Container | Purpose |
|---------|-----------|---------|
| `dev` | `wealth-ops-dev` | Python 3.13 + Poetry dev environment |
| `localstack` | `wealth-ops-localstack` | Emulates S3, DynamoDB locally |
| `test` | `wealth-ops-test` | Lightweight pytest runner (pre-commit) |

- **Config:** `docker-compose.yml` + `.devcontainer/devcontainer.json` (Includes `docker-outside-of-docker` & `node` features)
- **AWS Endpoint:** `http://localstack:4566` (auto-configured via env vars)
- **Persistence:** LocalStack data persists between restarts
- **Pre-commit:** Tests run automatically via `pytest-docker` hook (uses `moto` mocking)

## 3. The "One-Asset, One-Model" Policy
We train a unique XGBoost Classifier for each active asset in `DynamoDB:Config`.
- **Input:** 1-Day Candles (OHLCV) + Technicals (RSI, EMA, MACD, ADX, **OBV/Volume-Ratio**, **ATR**).
- **Target:** "Swing Probability" (Price > Current + 3% in 5 days).
- **Retrain Schedule:**
    - **On-Demand:** Retrain when backtest accuracy drops below 60%.
    - **Monthly Fallback:** Force retrain if 30 days pass without a refresh.

## 4. The "Swing Sniper" Trading Strategy
This system is optimized for an **Irish Tax Resident** managing personal capital. The default state is **100% CASH** unless a high-probability setup is confirmed.

### A. The Setup (Daily Intervals)
- **Candles:** We strictly use **1-Day (Daily)** OHLCV data.
- **Why:** To filter out HFT (High-Frequency Trading) noise and capture institutional flows.

### B. The "Gatekeeper" Trio (Entry Logic)
We require **Three Green Lights** to enter a trade. If any light is RED, we stay in CASH.

1.  **Macro Gate (The Regime):**
    -   **Rule:** S&P 500 Price > 200-day SMA.
    -   **Why:** Never buy stocks in a Bear Market.
2.  **Trend Gate (The Volatility):**
    -   **Rule:** ADX (14-day) > 20.
    -   **Why:** Never trade in a choppy, sideways market ("The Chop").
3.  **Asset Gate (The Alpha Specialist):**
    -   **Rule:** XGBoost Probability > 75%.
    -   **Why:** Only swing at the fat pitches.

### C. The Portfolio Guard (Risk Management)
Before execution, we apply **Correlation Controls**:
1.  **Sector Limit:** Max **1 Position** per Sector (e.g., Tech, Finance, Energy).
    -   *If multiple signals:* Pick the one with the highest Probability Score.
2.  **News Veto (LLM Sentiment Check):** (See `specs/ml-compute-strategy.md`)
    -   **Mechanism:** DeepSeek-V3 or Gemini Flash API.
    -   **Why:** Cheaper and higher quality than running FinBERT on Lambda.
    -   **Trigger:** Only analyzed if a BUY signal is present.

### D. The Execution (Trade Management)
-   **Position Sizing (Risk-Based):**
    -   **Max Risk Per Trade:** 2% of total portfolio.
    -   **Formula:** `Position Size = (Portfolio × 2%) / (ATR × 2)`
-   **Holding Period:** 3 to 10 Days (Swing Trade).
-   **Exit Strategy:**
    -   **Take Profit:** Sell 50% at +5%, Sell remainder at Trend Reversal.
    -   **Stop Loss:** Dynamic exit at **Entry Price - (2 × ATR)**. Adapts to each asset's volatility.
    -   **Time Stop:** Close position if no movement after 10 days.
