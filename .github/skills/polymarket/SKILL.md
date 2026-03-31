# Polymarket Daily Analysis

Self-improving Polymarket analysis system that scans markets, runs statistical/sentiment/arbitrage analysis, tracks prediction accuracy, and auto-tunes its parameters.

## What it does

1. **Market Scanning** — Fetches markets from Polymarket Gamma API, filters by probability, volume, time-to-expiry, and noise patterns
2. **Time Series Analysis** — SMA, volatility, momentum, z-score, mean reversion scoring
3. **Sentiment Analysis** — Rule-based NLP on RSS news feeds (Google News, Reuters, Bloomberg)
4. **Arbitrage Detection** — Spread anomalies, cross-market correlation via fuzzy matching, Kelly criterion
5. **Prediction Tracking** — Records daily predictions, checks resolved markets, computes hit rate & Brier score
6. **Self-Improvement** — Adjusts scoring weights, probability thresholds, volume filters based on accuracy metrics; optionally queries Copilot API (max 3 calls/day)
7. **HTML Report** — Dark-theme report with 5 sections: opportunities, performance, improvements, arbitrage, sentiment
8. **Email Delivery** — Sends report via SendGrid REST API

## Schedule

Runs daily at **22:00 TR** (19:00 UTC) via GitHub Actions. Can also be triggered manually via `workflow_dispatch`.

## Scripts

| File | Purpose |
|------|---------|
| `scripts/main.py` | Orchestrator — runs full pipeline |
| `scripts/scanner.py` | Market scanning & filtering |
| `scripts/analyzer.py` | Time series & statistical analysis |
| `scripts/sentiment.py` | RSS-based sentiment scoring |
| `scripts/arbitrage.py` | Spread anomaly & Kelly criterion |
| `scripts/predictor.py` | Prediction tracking & accuracy |
| `scripts/self_improve.py` | Config auto-tuning & Copilot suggestions |
| `scripts/reporter.py` | HTML report generation |
| `scripts/mailer.py` | SendGrid email delivery |
| `scripts/http_client.py` | urllib-based HTTP wrapper |

## Configuration

All tunable parameters live in `data/config.json`. The self-improvement engine modifies this file automatically based on prediction accuracy.

## Requirements

- Python 3.12 (stdlib only — no pip packages)
- `SENDGRID_API_KEY` repository secret
- `GITHUB_TOKEN` (auto-provided by Actions)
