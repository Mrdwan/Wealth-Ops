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

## 3. The "One-Asset, One-Model" Policy (Gray Box, Multi-Asset)
We train a unique XGBoost Classifier for each active asset in `DynamoDB:Config`.
The system is a **Gray Box**: strict human-defined rules (Hard Guards) wrap a learned model (Soft Skills). The model scores probability; the guards decide if we act on it.

The system supports **multiple asset classes**. Each asset carries a **Profile** that controls which features are computed, which guards are enforced, and how the regime is interpreted. The engine is the same — the profile configures it.

- **Target:** "Swing Probability" — `High > Close + 3%` within 5 trading days.
- **Retrain Schedule:**
    - **On-Demand:** Retrain when backtest accuracy drops below 60%.
    - **Monthly Fallback:** Force retrain if 30 days pass without a refresh.

### 3.1 Asset Profiles

Each asset in `DynamoDB:Config` carries a profile that determines its behavior across the entire pipeline: data ingestion, feature engineering, guard evaluation, and execution.

| Field | Description | Options |
|-------|-------------|---------|
| `asset_class` | Instrument category | `EQUITY`, `COMMODITY`, `FOREX` |
| `regime_index` | Ticker used for the Macro Gate | `SPY`, `DXY`, or custom |
| `regime_direction` | When to buy relative to the regime index | `BULL` (index > 200 SMA), `BEAR` (index < 200 SMA), `ANY` (skip gate) |
| `vix_guard` | Whether the Panic Guard (VIX < 30) applies | `true`, `false` |
| `event_guard` | Whether the Earnings Guard applies | `true`, `false` |
| `volume_features` | Whether OBV and Volume Ratio are computed | `true`, `false` |
| `benchmark_index` | Ticker for Relative Strength ratio | `SPY`, `DXY`, or `null` |
| `concentration_group` | Category for the Concentration Limit | Sector name, commodity type, or Forex pair family |

#### Pre-Built Profiles

| Profile | `regime_index` | `regime_dir` | `vix_guard` | `event_guard` | `volume` | `benchmark` | Example Tickers |
|---------|---------------|-------------|------------|--------------|---------|------------|-----------------|
| **EQUITY** | SPY | BULL | true | true | true | SPY | AAPL, MSFT, JPM |
| **COMMODITY_HAVEN** | DXY | BEAR | false | false | true (ETF) | DXY | GLD, SLV |
| **COMMODITY_CYCLICAL** | SPY | BULL | true | false | true (ETF) | DXY | USO, COPX |
| **FOREX** *(placeholder)* | — | ANY | false | false | false | DXY | EUR/USD, GBP/USD |

**Design rationale:**
- **COMMODITY_HAVEN** uses `DXY` with direction `BEAR` because Gold/Silver rally when the dollar weakens. The Macro Gate inverts: `DXY_Close < SMA(DXY, 200)` = weak dollar = bullish for gold.
- **COMMODITY_CYCLICAL** uses `SPY` with direction `BULL` because Oil/Copper are economically sensitive — they drop with the economy. Same regime as equities.
- **FOREX** uses `ANY` because currency pairs are driven by interest rate differentials, not equity regime. The Macro Gate is skipped entirely. *(Placeholder — not implemented until Phase 5.)*

> **Irish Tax Warning:** GLD, USO, SLV are **ETFs**, subject to **41% exit tax** + 8-year deemed disposal under Irish law. This conflicts with the Core Philosophy ("Minimize ETFs, 33% CGT"). Consider trading commodity **CFDs** (taxed at 33% CGT) or accept the tax drag for diversification. The profile system is instrument-agnostic — it works with ETFs, CFDs, or futures.

### 3.2 Feature Vector (Per Asset, Per Day)

Every feature is computed from **1-Day (Daily) OHLCV** data. No intraday data. The feature set is **profile-dependent**.

#### Base Features (All Asset Classes — 11 Features)

| # | Feature | Formula | Rationale |
|---|---------|---------|-----------|
| 1 | RSI (14) | Standard Wilder RSI, 14-period | Overbought/oversold momentum |
| 2 | EMA_8 | Exponential Moving Average, 8-period | Short-term trend |
| 3 | EMA_20 | Exponential Moving Average, 20-period | Medium-term trend |
| 4 | EMA_50 | Exponential Moving Average, 50-period | Long-term trend |
| 5 | MACD Histogram | `EMA_12 - EMA_26 - Signal_9` | Momentum direction |
| 6 | ADX (14) | Average Directional Index, 14-period | Trend strength |
| 7 | ATR (14) | Average True Range, 14-period | Volatility (used for stops) |
| 8 | **Upper Wick Ratio** | `(High - Max(Open, Close)) / (High - Low)` | Shooting Star detection (bearish rejection) |
| 9 | **Lower Wick Ratio (Hammer)** | `(Min(Open, Close) - Low) / (High - Low)` | Hammer detection (bullish reversal). Value > 0.6 = strong bounce. |
| 10 | **EMA Fan (Boolean)** | `is_bullish_fan = (EMA_8 > EMA_20 > EMA_50)` | Aligned trend — all timeframes agree |
| 11 | **Distance from 20d Low** | `dist_from_20d_low = (Close - Min(Low, 20d)) / Close` | Donchian Channel Low proximity |

#### Class-Specific Features

| # | Feature | Formula | Applies To | Rationale |
|---|---------|---------|-----------|-----------|
| 12 | OBV | On Balance Volume (cumulative) | EQUITY, COMMODITY (`volume_features=true`) | Volume confirmation. Requires exchange-traded volume. |
| 13 | Volume Ratio | `Volume / SMA(Volume, 20)` | EQUITY, COMMODITY (`volume_features=true`) | Relative volume spike detection. |
| 14 | **Relative Strength** | `rs_ratio = (Asset_Close / Benchmark_Close)` | ALL (benchmark varies by profile) | EQUITY: vs SPY. COMMODITY/FOREX: vs DXY. |

#### Feature Count by Profile

| Profile | Base | Volume (OBV + Vol Ratio) | RS | Total |
|---------|------|------------------------|----|-------|
| EQUITY | 11 | 2 | 1 (vs SPY) | **14** |
| COMMODITY | 11 | 2 (ETF exchange volume) | 1 (vs DXY) | **14** |
| FOREX | 11 | 0 (no centralized volume) | 1 (vs DXY) | **12** |

**Edge-Case Rules:**
- If `(High - Low) == 0` (doji with no range), set both wick ratios to `0.0`.
- `rs_ratio` is normalized to a rolling 20-day z-score to make it comparable across assets.
- FOREX models are trained with 12 features. The "One Asset, One Model" policy means each model's feature vector matches its profile — no padding, no placeholder values.

## 4. The "Swing Sniper" Trading Strategy (Multi-Asset)
This system is optimized for an **Irish Tax Resident** managing personal capital. The default state is **100% CASH** unless a high-probability setup is confirmed. All rules are **profile-conditional** — the asset's profile (Section 3.1) determines which guards apply and how they behave.

### A. The Setup (Daily Intervals)
- **Candles:** We strictly use **1-Day (Daily)** OHLCV data.
- **Why:** To filter out HFT noise and capture institutional flows.
- **Applies to:** All asset classes. Commodity ETFs trade on exchanges (same daily bars). Forex (future) uses the daily session close.

### B. The Hard Guards (Pass/Fail Gates)
These are **non-negotiable**. If **any applicable** guard is RED, the ML score is ignored and we stay in CASH. Guards are **profile-conditional** — each asset's profile determines which guards are evaluated.

| # | Guard | Scope | Rule | Condition | Fail Action |
|---|-------|-------|------|-----------|-------------|
| 1 | **Macro Gate (Regime)** | Market | `Regime_Index > SMA(Regime_Index, 200)` if `BULL`; inverted if `BEAR` | `regime_dir != ANY` | Halt buying for this asset class. Wrong regime. |
| 2 | **Panic Guard (VIX)** | Market | `VIX_Close < 30` | `vix_guard = true` | Halt buying for flagged assets. Extreme fear. |
| 3 | **Exposure Cap** | Portfolio | `count(open_positions) < 4` | Always | Halt all buying. Max total risk = 4 × 2% = 8%. |
| 4 | **Trend Gate (Volatility)** | Per Asset | `ADX_14 > 20` | Always | Skip asset. No trend to ride. |
| 5 | **Event Guard (Earnings)** | Per Asset | `Days_to_Earnings >= 7` | `event_guard = true` | Skip asset. Binary event risk. |
| 6 | **Pullback Zone (Extension)** | Per Asset | `(Close - EMA_8) / EMA_8 <= 0.05` | Always | Skip asset. Overextended above 8-EMA. |

#### How the Macro Gate Adapts by Profile

| Profile | Regime Index | Direction | Rule in Practice |
|---------|-------------|-----------|-----------------|
| EQUITY | SPY | BULL | `SPY_Close > SMA(SPY, 200)` → PASS. Standard bull market filter. |
| COMMODITY_HAVEN | DXY | BEAR | `DXY_Close < SMA(DXY, 200)` → PASS. Weak dollar = Gold/Silver tailwind. |
| COMMODITY_CYCLICAL | SPY | BULL | Same as equity. Oil/Copper need a healthy economy. |
| FOREX *(future)* | — | ANY | Gate **skipped**. Currency regimes are rate-driven, not equity-driven. |

**Notes:**
- **Evaluation Order:** Market-level guards (1-2) checked once per day. Portfolio-level (3) checked once. Per-asset guards (4-6) checked for each candidate.
- **Skipped guards are treated as PASS.** A COMMODITY_HAVEN with `vix_guard=false` bypasses the Panic Guard — it does not fail it.
- **Pullback Zone is one-sided.** Only blocks overextension to the **upside**.
- **Data Staleness Policy:** If any market-level data (S&P 500, VIX, DXY) is stale > 24 hours, the corresponding guard defaults to **FAIL**. Alert via Telegram. Never assume stale data is safe.
- **Earnings Refresh:** `next_earnings_date` must be refreshed **daily** for all EQUITY assets. Does not apply to COMMODITY or FOREX.

### C. The Soft Gate (ML Scoring)
Only evaluated if **all applicable Hard Guards pass** for a given asset.

-   **Rule:** `XGBoost_Calibrated_Probability > 0.75` (75%).
-   **Why:** Only swing at the fat pitches. The model uses the feature vector defined by the asset's profile (Section 3.2).
-   **Calibration Requirement:** Platt Scaling applied post-training. Calibration validated via reliability diagrams during backtesting — **per profile class**. Equity models and commodity models are calibrated independently.

### D. The Portfolio Guard (Risk Management)
Before execution, we apply **Concentration & Sizing Controls**:

1.  **Concentration Limit:** Max **1 Position** per concentration group.
    -   EQUITY: group = **Sector** (Tech, Finance, Energy, etc.)
    -   COMMODITY: group = **Commodity Type** (Precious Metals, Energy, Agriculture)
    -   FOREX: group = **Base Currency Family** (EUR-pairs, GBP-pairs, etc.)
    -   *If multiple signals in the same group:* Pick the one with the highest Probability Score.
2.  **Position Cap (Gap-Through Protection):** `Position_Value <= 15% of Portfolio`.
    -   **Formula:** `Position_Size = min(ATR_Size, Portfolio × 0.15 / Entry_Price)` where `ATR_Size = (Portfolio × 0.02) / (ATR_14 × 2)`.
    -   **Applies to:** All exchange-traded assets (equities + commodity ETFs) that gap overnight. For Forex (future, 24h trading), this cap may be relaxed — lower gap risk.
3.  **News Veto (LLM Sentiment Check):** (See `specs/ml-compute-strategy.md`)
    -   **Mechanism:** DeepSeek-V3 or Gemini Flash API.
    -   **Trigger:** Only analyzed if a BUY signal survives all prior gates. Applies to all asset classes.

### E. The Execution — "Trap Order" (Trade Management)
We do **not** use market orders. We use a **confirmation-based entry** to avoid false breakouts.

> **Multi-Asset Note:** The Trap Order logic is identical for equities and commodity ETFs (both exchange-traded, discrete sessions, overnight gaps). Forex-specific adjustments are noted as placeholders for Phase 5.

#### Entry: BUY STOP LIMIT (The Trap)
-   **Trigger:** All applicable Hard Guards passed AND XGBoost > 75% AND Portfolio Guard cleared.
-   **Order:** Place a **BUY STOP LIMIT** at:
    ```
    Stop Price  = High_of_Signal_Candle + (0.02 × ATR_14)
    Limit Price = Stop Price + (0.05 × ATR_14)
    ```
-   **Logic:** The price must **break the signal candle's high** (confirming momentum) before we enter. The ATR-scaled buffer prevents noise fills.
-   **TTL:**
    -   EQUITY / COMMODITY: **1 trading session** (by market close of the next day).
    -   FOREX *(future)*: **24 clock hours** (Forex is ~24h/5d; session-based TTL doesn't apply).

#### Gap-Through Policy
-   If the asset opens **above** the Limit Price (gap-through), the order does not fill. **This is by design.**
-   Applies primarily to EQUITY and COMMODITY (discrete sessions with overnight gaps).
-   FOREX *(future)*: Gap-throughs are rare outside weekend gaps. The policy still applies but triggers infrequently.

#### Position Sizing (Risk-Based, Dual Constraint)
-   **Max Risk Per Trade:** 2% of total portfolio.
-   **Primary Formula:** `ATR_Size = (Portfolio × 0.02) / (ATR_14 × 2)`
-   **Position Cap:** `Cap_Size = (Portfolio × 0.15) / Entry_Price`
-   **Final Size:** `Position_Size = min(ATR_Size, Cap_Size)`
-   **Why dual constraint:** The ATR formula limits *expected* loss. The position cap limits *gap-through* loss. Both needed for discrete-session assets. For Forex (future), the cap may be relaxed.

#### Exit Strategy
-   **Take Profit (ADX-Scaled):** Sell 50% at `Entry_Price + (TP_mult × ATR_14)` where:
    ```
    TP_mult = clamp(2 + ADX_14 / 30, 2.5, 4.5)
    ```
    | ADX | TP Multiplier | Behavior |
    |-----|--------------|----------|
    | 20 | 2.67 | Weak trend — take profit early. |
    | 30 | 3.0 | Moderate trend — standard target. |
    | 40 | 3.33 | Strong trend — give it room. |
    | 50+ | 4.5 (capped) | Very strong trend — max target. |

    Applies to all asset classes. ADX is a base feature (Section 3.2).
-   **Trailing Exit (Chandelier):** For the remaining 50%, trail a **Chandelier Stop** at `Highest_High_Since_Entry - (2 × ATR_14)`. Applies to all.
-   **Stop Loss:** Dynamic exit at `Entry_Price - (2 × ATR_14)`. This is a **market order** (not a stop-limit) to guarantee fill, even through a gap-down. Applies to all.
-   **Time Stop:** Close position at market if no movement after 10 trading days. Applies to all.

### F. Risk Matrix by Asset Class

| Risk | EQUITY | COMMODITY (ETF) | FOREX *(future)* |
|------|--------|----------------|-----------------|
| **Overnight Gap** | **HIGH.** Earnings, lawsuits, fraud. Mitigated by: Event Guard, Position Cap (15%), News Veto. | **MODERATE.** ETFs gap at open but lack idiosyncratic events (no CEO, no earnings). Mitigated by: Position Cap (15%). | **LOW.** 24h trading; gaps only on weekends. Position Cap still applies. |
| **Gap-Up Entry Miss** | **MODERATE.** Institutional demand causes gap-ups. Accepted by design (Gap-Through Policy). | **MODERATE.** Same mechanism for commodity ETFs. | **LOW.** Continuous pricing means stop-limit fills reliably. |
| **Beta Correlation** | **HIGH.** Stocks correlated to S&P. Mitigated by: Macro Gate (SPY), Exposure Cap, Concentration Limit. | **LOW (Haven) / MODERATE (Cyclical).** Gold is *negatively* correlated — it hedges equity drawdowns. Oil correlates with SPY. Profile-based regime handles both. | **LOW.** Forex driven by rate differentials, not equity beta. |
| **Regime Mismatch** | N/A. Macro Gate is native to equities. | **SOLVED.** Profile inverts regime for havens (`DXY < 200 SMA`), matches equities for cyclicals. | N/A. Regime skipped (`ANY`). |
| **Event Risk** | **HIGH.** Earnings are the #1 gap source. Event Guard blocks 7 days before. | **LOW.** No earnings. Event Guard skipped. | **LOW.** Central bank dates are scheduled. *(Future: add economic calendar guard in Phase 5.)* |
| **Volume Data** | Available. Exchange-traded. | Available. ETF volume is a valid proxy for participation. | **UNAVAILABLE.** No centralized volume. OBV and Volume Ratio excluded (12-feature vector). |
| **Tax (Ireland)** | **33% CGT.** Preferred under Core Philosophy. | **41% exit tax** if ETF (GLD, USO). Consider CFDs (33% CGT). | **33% CGT** if CFD. Favorable. |

**Cross-Class Portfolio Benefit:** Holding EQUITY (risk-on) + COMMODITY_HAVEN (risk-off) positions simultaneously provides **natural hedging**. When equities drawdown, Gold tends to rally. The Exposure Cap (4 total) allows a mixed portfolio — e.g., 2 equities + 1 Gold + 1 cash = genuine diversification within a single system.

**Accepted residual risks:**
- A single position can lose up to ~4.5% of portfolio on an overnight gap (capped by Position Cap).
- A correlated selloff across all 4 positions can cause ~8% portfolio drawdown (capped by Exposure Cap).
- The Macro Gate is lagging by design (200 SMA). Short drawdowns before the gate triggers are accepted.
