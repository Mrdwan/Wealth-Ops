---
trigger: model_decision
description: when working on coding
---

# 🛡️ Code Standards & Quality Guidelines

## 1. Core Principles (SOLID)
- **Single Responsibility (SRP):** Each module/class must do ONE thing.
  - *Bad:* `class Trader` that fetches data, calculates RSI, and executes orders.
  - *Good:* `class DataFetcher`, `class IndicatorCalculator`, `class OrderExecutor`.
- **Dependency Inversion (DIP):** High-level modules must not depend on low-level modules. Both should depend on abstractions.
  - *Rule:* Never import `boto3` or `requests` directly in business logic. Inject them as dependencies or Protocols.

## 2. Python Style & Typing
- **Strict Typing:** All function signatures MUST have type hints.
  - *Required:* `def calculate_rsi(prices: list[float], period: int) -> float:`
  - *Forbidden:* `def calculate_rsi(prices, period):`
- **Docstrings:** Google Style docstrings required for all public methods.
  - Must include `Args:`, `Returns:`, and `Raises:` sections.
- **Error Handling:** Never use bare `try: except:`. Catch specific errors (e.g., `ClientError`, `ValueError`) and log them with context.

## 3. Testing Strategy (Zero-Bug Policy)
- **Framework:** `pytest` is the only approved runner.
- **Coverage:** Target **100% Branch Coverage** for `src/modules/*`.
- **Mocking (The Iron Rule):**
  - **STRICTLY FORBIDDEN:** Network calls in tests. You must use `unittest.mock` or `moto` (for AWS) to stub all external interactions.
  - *Why:* Tests must pass offline and cost $0.
- **Fixtures:** Use `conftest.py` to share mock data (e.g., a static DataFrame of 5 days of Apple stock) rather than generating random data.

## 4. AWS & Infrastructure
- **Boto3:** Always instantiate clients in a `Shared` or `Config` module, never inside a loop.
- **Logging:** Use the standard `logging` library with JSON formatters (for CloudWatch). Do not use `print()`.
