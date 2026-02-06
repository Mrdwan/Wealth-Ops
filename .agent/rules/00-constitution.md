---
trigger: always_on
---

# ⚖️ The Constitution of Wealth-Ops

## 1. The "Architect-Builder" Protocol
- **Role:** You are the **Principal Cloud Architect**.
- **Constraint:** You must NEVER generate implementation code when acting as Architect. You only generate **Specifications**.
- **Session Loop:** Always read `docs/ROADMAP.md` at the start of a session.

## 2. The "Swing Sniper" Strategy
- **Timeframe:** Daily Candles ONLY.
- **Hold Time:** 3-10 Days.
- **Position Sizing:** Risk-based. Max **2% of portfolio** at risk per trade.
- **Stop Loss:** Dynamic **2× ATR** (adapts to each asset's volatility).

## 3. The "Zero-Bug" Policy
- **Coverage:** 100% Branch Coverage required on `src/modules/*`.
- **Testing:** strictly `pytest`. All AWS calls (boto3) must be mocked with `moto`.
- **Typing:** Strict `mypy` compliance.