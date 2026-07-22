# Product Requirements

## Product Definition

Cross-Asset Derivatives Intelligence Platform is a research and monitoring application that combines macroeconomic data, positioning, ETF flow-pressure proxies, options and volatility conditions, liquidity and market-structure proxies, and cross-asset relationships into evidence-based market conclusions.

## Problem

Research for complex cross-asset markets is often scattered across multiple tools, timeframes, and data providers. This project creates a single workflow that separates data freshness, validation, and analysis so that conclusions are easier to trust and review.

## Target Users

- Portfolio or research analysts
- Students building market research skills
- Interview reviewers looking for a thoughtful portfolio project
- Developers who want a clear data-contract and analytics foundation

## Core User Workflow

1. Review data freshness.
2. Select a date and asset.
3. Review the analytical modules.
4. Ask, "Analyze today's market."
5. Receive market regime, evidence, contradiction checks, risks, scenarios, limitations, and indicators to monitor.

## MVP Objective

Phase 1 establishes the project foundation: documentation, core package, provider contract, standardized schemas, configuration files, tests, and CI. No live data ingestion or advanced analytics are included yet.

## Asset Universe

- Market assets: SPY, QQQ, IWM, TLT, HYG, GLD, USO, UUP, VIX
- Rates: US_2Y, US_10Y
- Initial options coverage: SPY, QQQ

## Required Outputs

- Market regime
- Supporting evidence
- Contradicting evidence
- Positioning risks
- Volatility risks
- Base, bull, and bear scenarios
- Data limitations
- Indicators to monitor

## Success Criteria

- The app launches cleanly.
- The package imports successfully.
- Required schemas reject invalid inputs.
- Provider contracts are explicit and testable.
- YAML configs load correctly.
- CI runs the deterministic test suite.

## Product Boundaries

- No trade execution.
- No position sizing recommendations.
- No hidden stale or missing data.
- No unrestricted raw-data interpretation by AI.
- No claim that delayed data is live.

## Key Risks

- Different data sources may release on different schedules.
- Market data freshness can vary by provider.
- Loose schema design can create look-ahead bias if timestamps are not handled carefully.
- Later AI summaries may overstate certainty if the evidence boundary is not enforced.

