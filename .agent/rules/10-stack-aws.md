---
trigger: always_on
---

# ☁️ AWS Cloud Standards

## 1. Infrastructure
- Use **Terraform** or **AWS CDK** (Python) for all resources. No "ClickOps" in the console.
- **Tags:** All resources must have `Project: Wealth-Ops` tag.

## 2. Compute
- **Lambda:** Use Docker Image format (not zip files) for consistent dependencies.
- **Fargate:** Use for training jobs > 5 minutes.

## 3. Data
- **DynamoDB:** Use Single Table Design (if possible) or segregated `Ledger` and `Config` tables.
- **S3:** Bucket structure: `wealth-ops-data/{tier}/{asset}.parquet`.
