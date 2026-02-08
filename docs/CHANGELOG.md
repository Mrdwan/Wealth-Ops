# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2026-02-08

### Fixed
- Fixed devcontainer issue with Antigravity Server symlink to ensure tool availability in the container.
- Resolved recursive `cdk-synth` bundling issue by ignoring `cdk.out` in `.dockerignore` and `.gitignore`.
- Fixed all `pre-commit` hook errors, including missing `mypy` stubs and `ruff` formatting issues.

### Added
- configured DevContainer with `docker-outside-of-docker` and `node` features for full CDK and Docker support.
- Added **Rule 4: The "Living Documentation" Clause** to the `00-constitution.md`, enforcing documentation updates at the end of every session.
