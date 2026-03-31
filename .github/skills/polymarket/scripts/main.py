#!/usr/bin/env python3
"""
Main orchestrator — runs the full Polymarket analysis pipeline.
Usage: python main.py [--dry-run] [--no-email]
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


def load_config():
    config_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data', 'config.json')
    )
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f), config_path


def main():
    parser = argparse.ArgumentParser(description='Polymarket Daily Analysis Pipeline')
    parser.add_argument('--dry-run', action='store_true', help='Run analysis but do not send email')
    parser.add_argument('--no-email', action='store_true', help='Skip email sending')
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    print(f"=== Polymarket Analysis Pipeline — {now.strftime('%Y-%m-%d %H:%M UTC')} ===\n")

    # 1. Load config
    print("[1/8] Loading config...")
    config, config_path = load_config()

    # 2. Check past predictions & compute accuracy
    print("[2/8] Checking past predictions...")
    lookback = config.get('self_improve', {}).get('lookback_days', 30)
    accuracy_metrics = predictor.check_past_predictions(lookback_days=lookback)
    total_preds = accuracy_metrics.get('total_predictions', 0)
    hit_rate = accuracy_metrics.get('hit_rate', 0)
    print(f"  Predictions checked: {total_preds}, Hit rate: {hit_rate*100:.1f}%")

    # 3. Self-improvement
    print("[3/8] Running self-improvement...")
    improvements = self_improve.run_self_improvement(accuracy_metrics, config)
    if improvements['total_adjustments'] > 0:
        # Reload config after self-improvement modified it
        config, config_path = load_config()
    print(f"  Config adjustments: {improvements['total_adjustments']}")
    print(f"  Copilot suggestions: {len(improvements.get('copilot_suggestions', []))}")

    # 4. Scan markets
    print("[4/8] Scanning Polymarket...")
    scan_results = scanner.scan_markets(config)
    print(f"  Found {len(scan_results)} opportunities")

    if not scan_results:
        print("\nNo opportunities found. Generating minimal report.")
        html, path = reporter.generate_report([], accuracy_metrics, improvements, {}, {}, config)
        if not args.dry_run and not args.no_email:
            mailer.send_report(html, config)
        print("Done.")
        return

    # 5. Statistical analysis
    print("[5/8] Running statistical analysis...")
    analyzer.record_prices(scan_results)
    analysis = analyzer.analyze_all(scan_results, config)
    print(f"  Analyzed {len(analysis)} markets")

    # 6. Sentiment analysis
    print("[6/8] Running sentiment analysis...")
    sentiment_data = sentiment.analyze_sentiment(scan_results, config)
    matched = sum(1 for v in sentiment_data.values() if v.get('matched_headlines'))
    print(f"  Sentiment data for {len(sentiment_data)} markets, {matched} with headlines")

    # 7. Arbitrage detection
    print("[7/8] Computing arbitrage scores...")
    arb_scores = arbitrage.compute_arbitrage_scores(scan_results)
    anomalies = sum(1 for v in arb_scores.values() if v.get('has_anomaly'))
    print(f"  Anomalies: {anomalies}")

    # 8. Create predictions & generate report
    print("[8/8] Creating predictions & report...")
    predictions = predictor.create_predictions(scan_results, analysis, sentiment_data, arb_scores, config)
    predictor.save_predictions(predictions)
    print(f"  {len(predictions)} predictions saved")

    html, report_path = reporter.generate_report(
        predictions, accuracy_metrics, improvements, arb_scores, sentiment_data, config
    )
    print(f"  Report: {report_path}")

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
