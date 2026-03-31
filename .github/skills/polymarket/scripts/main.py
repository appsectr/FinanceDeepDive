#!/usr/bin/env python3
"""
Main orchestrator — runs the full Polymarket analysis pipeline.
Usage: python main.py [--dry-run] [--no-email] [--learn]
"""
import json
import os
import sys
import argparse
from datetime import datetime, timezone

# All modules live in the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import scanner
import analyzer
import sentiment
import arbitrage
import predictor
import self_improve
import reporter
import mailer
import arxiv
import trader


def load_config():
    config_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data', 'config.json')
    )
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f), config_path


def run_learn_only():
    """Run only ArXiv research + self-improvement — no market scanning."""
    now = datetime.now(timezone.utc)
    print(f"=== Learn Mode — {now.strftime('%Y-%m-%d %H:%M UTC')} ===\n")

    # 1. Load config
    print("[1/3] Loading config...")
    config, _ = load_config()

    # 2. ArXiv paper research
    print("[2/3] Checking ArXiv for new papers...")
    arxiv_results = arxiv.check_arxiv(config)
    new_count = len(arxiv_results.get('new_papers', []))
    insights = arxiv_results.get('insights', [])
    print(f"  New papers: {new_count}, Total in DB: {arxiv_results.get('total_in_db', 0)}")
    for p in arxiv_results.get('new_papers', []):
        print(f"    + {p.get('title', '?')}")
    if insights:
        print(f"  Insights extracted: {len(insights)}")
        for ins in insights:
            print(f"    [{ins.get('insight_type')}] {ins.get('context', '')[:80]}")

    # 3. Self-improvement with ArXiv insights
    print("[3/3] Running self-improvement...")
    lookback = config.get('self_improve', {}).get('lookback_days', 30)
    accuracy_metrics = predictor.check_past_predictions(lookback_days=lookback)
    improvements = self_improve.run_self_improvement(accuracy_metrics, config, arxiv_results=arxiv_results)
    adj = improvements['total_adjustments']
    arxiv_changes = improvements.get('arxiv_changes', [])
    copilot_sug = improvements.get('copilot_suggestions', [])
    print(f"  Config adjustments: {adj}")
    for c in arxiv_changes:
        print(f"    ArXiv: {c.get('detail', '')} — {c.get('reason', '')}")
    for s in copilot_sug:
        print(f"    Copilot: {s.get('suggestion', '')[:80]}")

    print(f"\n=== Learn complete — {new_count} new papers, {adj} adjustments ===")


def main():
    parser = argparse.ArgumentParser(description='Polymarket Daily Analysis Pipeline')
    parser.add_argument('--dry-run', action='store_true', help='Run analysis but do not send email')
    parser.add_argument('--no-email', action='store_true', help='Skip email sending')
    parser.add_argument('--learn', action='store_true',
                        help='Only run ArXiv research + self-improvement, skip market analysis')
    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    if args.learn:
        return run_learn_only()

    print(f"=== Polymarket Analysis Pipeline — {now.strftime('%Y-%m-%d %H:%M UTC')} ===\n")

    # 1. Load config
    print("[1/10] Loading config...")
    config, config_path = load_config()

    # 2. Check past predictions & compute accuracy
    print("[2/10] Checking past predictions...")
    lookback = config.get('self_improve', {}).get('lookback_days', 30)
    accuracy_metrics = predictor.check_past_predictions(lookback_days=lookback)
    total_preds = accuracy_metrics.get('total_predictions', 0)
    hit_rate = accuracy_metrics.get('hit_rate', 0)
    print(f"  Predictions checked: {total_preds}, Hit rate: {hit_rate*100:.1f}%")

    # 3. ArXiv paper research (runs before self-improvement to feed insights)
    print("[3/10] Checking ArXiv for new papers...")
    arxiv_results = arxiv.check_arxiv(config)
    print(f"  New papers: {len(arxiv_results.get('new_papers', []))}, "
          f"Total in DB: {arxiv_results.get('total_in_db', 0)}")

    # 4. Self-improvement (uses accuracy metrics + ArXiv insights)
    print("[4/10] Running self-improvement...")
    improvements = self_improve.run_self_improvement(accuracy_metrics, config, arxiv_results=arxiv_results)
    if improvements['total_adjustments'] > 0:
        # Reload config after self-improvement modified it
        config, config_path = load_config()
    print(f"  Config adjustments: {improvements['total_adjustments']}")
    print(f"  ArXiv-based changes: {len(improvements.get('arxiv_changes', []))}")
    print(f"  Copilot suggestions: {len(improvements.get('copilot_suggestions', []))}")

    # 5. Scan markets
    print("[5/10] Scanning Polymarket...")
    scan_results = scanner.scan_markets(config)
    print(f"  Found {len(scan_results)} opportunities")

    if not scan_results:
        print("\nNo opportunities found. Generating minimal report.")
        html, path = reporter.generate_report([], accuracy_metrics, improvements, {}, {}, config)
        if not args.dry_run and not args.no_email:
            mailer.send_report(html, config)
        print("Done.")
        return

    # 6. Statistical analysis
    print("[6/10] Running statistical analysis...")
    analyzer.record_prices(scan_results)
    analysis = analyzer.analyze_all(scan_results, config)
    print(f"  Analyzed {len(analysis)} markets")

    # 7. Sentiment analysis
    print("[7/10] Running sentiment analysis...")
    sentiment_data = sentiment.analyze_sentiment(scan_results, config)
    matched = sum(1 for v in sentiment_data.values() if v.get('matched_headlines'))
    print(f"  Sentiment data for {len(sentiment_data)} markets, {matched} with headlines")

    # 8. Arbitrage detection
    print("[8/10] Computing arbitrage scores...")
    arb_scores = arbitrage.compute_arbitrage_scores(scan_results)
    anomalies = sum(1 for v in arb_scores.values() if v.get('has_anomaly'))
    print(f"  Anomalies: {anomalies}")

    # 9. Create predictions & generate report
    print("[9/10] Creating predictions & report...")
    predictions = predictor.create_predictions(scan_results, analysis, sentiment_data, arb_scores, config)
    predictor.save_predictions(predictions)
    print(f"  {len(predictions)} predictions saved")

    html, report_path = reporter.generate_report(
        predictions, accuracy_metrics, improvements, arb_scores, sentiment_data, config
    )
    print(f"  Report: {report_path}")

    # 10. Auto-trading (disabled by default)
    print("[10/10] Trading engine...")
    trade_results = trader.execute_trades(predictions, config)
    if trade_results.get('trades_executed', 0) > 0 or trade_results.get('trades_dry_run', 0) > 0:
        print(f"  Executed: {trade_results.get('trades_executed', 0)}, "
              f"Dry-run: {trade_results.get('trades_dry_run', 0)}, "
              f"Spent: ${trade_results.get('total_usd_spent', 0):.2f}")

    # Send email
    if not args.dry_run and not args.no_email:
        mailer.send_report(html, config)
    elif args.dry_run:
        print("  [DRY RUN] Email skipped")
    elif args.no_email:
        print("  [NO EMAIL] Email skipped")

    print(f"\n=== Pipeline complete — {len(predictions)} predictions, report saved ===")


if __name__ == '__main__':
    main()
