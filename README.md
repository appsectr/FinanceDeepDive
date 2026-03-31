# FinanceDeepDive

Self-improving Polymarket daily analysis system. Scans markets, runs statistical/sentiment/arbitrage analysis, tracks prediction accuracy, auto-tunes parameters, and sends a dark-theme HTML report to email every day at 22:00 TR.

## Quick Start

```bash
# Local dry run (no email)
python .github/skills/polymarket/scripts/main.py --dry-run

# Full run with email
SENDGRID_API_KEY=your_key python .github/skills/polymarket/scripts/main.py
```

## Architecture

```
.github/
  skills/polymarket/     # Skill definition
    SKILL.md
    scripts/             # All Python modules (stdlib only)
  workflows/
    daily-report.yml     # Cron: 22:00 TR daily
data/
  config.json            # Tunable parameters (auto-updated)
  predictions/           # Daily prediction JSONs
  history/               # Price history & improvement logs
  reports/               # Generated HTML reports
```

See [.github/skills/polymarket/SKILL.md](.github/skills/polymarket/SKILL.md) for details.