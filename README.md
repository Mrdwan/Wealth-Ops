# 🏛️ Wealth-Ops v2.0

**An AI-Powered, Cloud-Native Personal Hedge Fund optimized for Irish Tax Residents.**

> **Status:** Phase 0 (Infrastructure Setup)
> **License:** Private / MIT
> **Current Focus:** Building the AWS Foundation.

---

## 📖 The Mission
Wealth-Ops is not a "get rich quick" bot. It is a **Capital Preservation & Swing Trading Engine** designed to solve three specific problems for the individual investor in Ireland:

1.  **The Tax Trap:** Avoids ETFs (41% Deemed Disposal Tax) in favor of Direct Indexing (Individual Stocks @ 33% CGT).
2.  **The Fee Shark:** Enforces minimum trade sizes (€2k+) to minimize commission drag.
3.  **The Emotional Gap:** Uses an "AI Committee" to separate mathematical signal from human panic.

---

## 🧠 The Architecture (The Committee)

The system operates as a distributed "Committee of Agents" on AWS:

1.  **🛡️ The Regime Filter (Circuit Breaker):**
    * *Logic:* "Don't catch a falling knife."
    * *Role:* Checks S&P 500 vs. 200-day MA. If Bear Market, **hard block** on all buys.
2.  **🔭 The Scout (Data):**
    * *Role:* Fetches Daily Candles (Yahoo) and News Sentiment (RSS/APIs).
3.  **🎯 The Alpha Specialist (Math):**
    * *Core Tech:* XGBoost (One Model Per Asset).
    * *Strategy:* **"The Swing Sniper"** - Predicts if `High > Close + 3%` within 5 days.
4.  **⚖️ The Judge (Synthesis):**
    * *Role:* An LLM (Gemini/Claude) that reads the Specialist's math and the Scout's news to issue a final **Buy/Hold/Sell** verdict.

---

## 🛠️ Tech Stack

**Infrastructure:**
* **Cloud:** AWS (Lambda, Fargate, Step Functions).
* **IaC:** AWS CDK (Python).
* **Database:** DynamoDB (Single Table Design for Ledger & Config).
* **Storage:** S3 (Parquet Data Lake).

**Application:**
* **Language:** Python 3.13+.
* **ML Engine:** XGBoost.
* **Quality:** `pytest` (100% Branch Coverage), `mypy` (Strict Typing).

---

## 📂 Project Structure

This project follows the **Context-First** development protocol.

```text
wealth-ops-v2/
├── .devcontainer/          # 🐳 Dev Container (Docker-based dev environment)
├── .pre-commit-config.yaml # 🔒 Pre-commit hooks (ruff, mypy, poetry check)
├── .agent/                 # 🤖 The AI Context Kernel
│   └── rules/              # The "Laws" (Constitution, Code Standards)
├── docs/                   # 📜 The Truth (Architecture & Roadmap)
├── infra/                  # ☁️ Infrastructure as Code (CDK)
├── src/                    # 🧠 Application Logic
│   ├── modules/            # The Committee Members (Specialist, Scout, Judge)
│   └── shared/             # Shared Utilities (Logger, Config)
├── tests/                  # 🛡️ The Quality Gate (100% Coverage)
└── README.md
