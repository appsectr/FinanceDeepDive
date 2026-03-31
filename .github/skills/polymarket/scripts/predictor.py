"""
Prediction tracker — records daily predictions and measures accuracy.
Stores predictions as JSON in data/predictions/YYYY-MM-DD.json.
On each run, checks past predictions against resolved Polymarket markets.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_client


def _predictions_dir():
    base = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data', 'predictions')
    base = os.path.normpath(base)
    os.makedirs(base, exist_ok=True)
    return base


def save_predictions(predictions):
    """Save today's predictions list to data/predictions/YYYY-MM-DD.json."""
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    path = os.path.join(_predictions_dir(), f'{today}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(predictions, f, ensure_ascii=False, indent=1)
    print(f"Saved {len(predictions)} predictions to {path}")


def load_predictions(date_str):
    """Load predictions for a specific date."""
    path = os.path.join(_predictions_dir(), f'{date_str}.json')
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def list_prediction_dates():
    """Return sorted list of dates that have prediction files."""
    d = _predictions_dir()
    dates = []
    for fname in os.listdir(d):
        if fname.endswith('.json') and fname != 'accuracy_log.json':
            dates.append(fname.replace('.json', ''))
    dates.sort()
    return dates


def _check_market_resolved(condition_id):
    """Check if a market has resolved via Gamma API. Returns outcome or None."""
    try:
        url = f"https://gamma-api.polymarket.com/markets/{condition_id}"
        data = http_client.get_json_safe(url, timeout=10)
        if data is None:
            return None
        resolved = data.get('resolved', False)
        if not resolved:
            return None
        # outcome: "Yes" or "No"
        outcome = data.get('outcome')
        return outcome
    except Exception:
        return None


def check_past_predictions(lookback_days=30):
    """
    Check predictions from the last N days against market outcomes.
    Returns accuracy metrics dict.
    """
    now = datetime.now(timezone.utc)
    all_dates = list_prediction_dates()

    total = 0
    correct = 0
    brier_sum = 0.0
    results = []
    calibration_buckets = {}  # bucket → [actual_outcomes]

    for date_str in all_dates:
        try:
            pred_date = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if (now - pred_date).days > lookback_days:
            continue

        preds = load_predictions(date_str)
        for p in preds:
            if p.get('checked'):
                # Already resolved in a previous run
                total += 1
                if p.get('correct') is not None:
                    if p['correct']:
                        correct += 1
                    brier_sum += p.get('brier', 0)
                    # Calibration
                    bucket = round(p['confidence'] * 10) / 10  # round to nearest 0.1
                    calibration_buckets.setdefault(bucket, []).append(1.0 if p['correct'] else 0.0)
                continue

            outcome = _check_market_resolved(p.get('market_id', ''))
            if outcome is None:
                continue  # not resolved yet

            # Determine if prediction was correct
            predicted_side = p.get('predicted_side', '').upper()
            actual = outcome.upper() if outcome else ''
            is_correct = (predicted_side == actual)

            # Brier score component: (predicted_prob - actual)^2
            predicted_prob = p.get('predicted_prob', 0.5)
            actual_binary = 1.0 if is_correct else 0.0
            brier = (predicted_prob - actual_binary) ** 2

            # Update prediction record
            p['checked'] = True
            p['actual_outcome'] = outcome
            p['correct'] = is_correct
            p['brier'] = round(brier, 4)

            total += 1
            if is_correct:
                correct += 1
            brier_sum += brier

            bucket = round(p.get('confidence', predicted_prob) * 10) / 10
            calibration_buckets.setdefault(bucket, []).append(actual_binary)

            results.append({
                'date': date_str,
                'question': p.get('question', ''),
                'predicted': predicted_side,
                'actual': actual,
                'correct': is_correct,
                'brier': round(brier, 4),
            })

        # Re-save with updated checked status
        pred_path = os.path.join(_predictions_dir(), f'{date_str}.json')
        with open(pred_path, 'w', encoding='utf-8') as f:
            json.dump(preds, f, ensure_ascii=False, indent=1)

    # Compute metrics
    hit_rate = correct / total if total > 0 else 0.0
    avg_brier = brier_sum / total if total > 0 else 0.0

    # Calibration: for each confidence bucket, actual hit rate
    calibration = {}
    for bucket, outcomes in sorted(calibration_buckets.items()):
        if outcomes:
            calibration[str(bucket)] = {
                'expected': bucket,
                'actual': round(sum(outcomes) / len(outcomes), 4),
                'count': len(outcomes),
            }

    metrics = {
        'total_predictions': total,
        'correct': correct,
        'hit_rate': round(hit_rate, 4),
        'avg_brier_score': round(avg_brier, 4),
        'calibration': calibration,
        'recent_results': results[-20:],  # last 20 for report
        'timestamp': now.isoformat(),
    }

    # Save accuracy log
    log_path = os.path.join(_predictions_dir(), 'accuracy_log.json')
    log = []
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            log = json.load(f)
    log.append({
        'date': now.strftime('%Y-%m-%d'),
        'hit_rate': metrics['hit_rate'],
        'avg_brier': metrics['avg_brier_score'],
        'total': metrics['total_predictions'],
    })
    # Keep last 90 entries
    log = log[-90:]
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=1)

    return metrics


def create_predictions(scan_results, analysis, sentiment_data, arb_scores, config=None):
    """
    Create prediction records from today's analysis.
    Incorporates research-backed improvements:
    - Dynamic weights from per-signal accuracy tracking (Greedy-Weighted Ensemble)
    - News volume as independent predictor (Oil Price NLP paper)
    - Signal agreement/divergence detection for abstention
    - Regime-aware confidence adjustment
    Returns list of prediction dicts to be saved.
    """
    if config is None:
        config = {}

    # Try dynamic weights first; fall back to static config weights
    try:
        from analyzer import compute_dynamic_weights
        weights = compute_dynamic_weights(config)
    except Exception:
        weights = config.get('scoring', {}).get('weights', {})

    w_stat = weights.get('statistical', 0.40)
    w_sent = weights.get('sentiment', 0.20)
    w_arb = weights.get('arbitrage', 0.25)
    w_vol = weights.get('volume', 0.15)

    # News volume weight — carved from volume weight (research: news count is robust predictor)
    w_news_vol = 0.05
    w_vol = max(0.05, w_vol - w_news_vol)

    predictions = []
    # Normalise volumes for scoring
    volumes = [r['volume'] for r in scan_results]
    max_vol = max(volumes) if volumes else 1

    for r in scan_results:
        mid = r['id']
        side_key = r['side'].lower()

        # Statistical score
        stat = analysis.get(mid, {})
        stat_score = stat.get(f'stat_score_{side_key}', 0.5)

        # Regime info
        regime = stat.get('regime', 'unknown')

        # Sentiment score (convert -1..+1 to 0..1)
        sent = sentiment_data.get(mid, {})
        raw_sent = sent.get('score', 0.0)
        if side_key == 'yes':
            sent_score = (raw_sent + 1.0) / 2.0
        else:
            sent_score = (1.0 - raw_sent) / 2.0

        # News volume score (independent of sentiment direction)
        news_vol_score = sent.get('news_volume_score', 0.0)

        # Arbitrage score
        arb = arb_scores.get(mid, {})
        arb_score = arb.get('arb_score', 0.0)

        # Volume score (normalised)
        vol_score = r['volume'] / max_vol if max_vol > 0 else 0

        # Composite score (5-signal ensemble)
        composite = (
            stat_score * w_stat +
            sent_score * w_sent +
            arb_score * w_arb +
            vol_score * w_vol +
            news_vol_score * w_news_vol
        )
        composite = round(composite, 4)

        # --- Signal agreement / divergence detection ---
        # If signals strongly disagree, this market is uncertain
        signals = [stat_score, sent_score, arb_score]
        signal_mean = sum(signals) / len(signals) if signals else 0.5
        signal_variance = sum((s - signal_mean) ** 2 for s in signals) / len(signals) if signals else 0
        signals_agree = signal_variance < 0.04  # low variance = agreement

        # --- Confidence with regime & agreement adjustment ---
        data_points = stat.get('data_points', 0)
        data_bonus = min(0.1, data_points * 0.01)
        confidence = min(0.95, composite + data_bonus)
        confidence = max(0.1, confidence)

        # Regime penalty: in volatile markets, reduce confidence
        if regime == 'volatile':
            confidence *= 0.85
        elif regime == 'calm':
            confidence = min(0.95, confidence * 1.05)

        # Divergence penalty: when signals disagree, reduce confidence
        if not signals_agree:
            confidence *= 0.90

        confidence = round(max(0.1, min(0.95, confidence)), 4)

        # --- Abstention flag ---
        # Markets where we should NOT trade (inspired by calibration papers)
        abstain = False
        abstain_reasons = []
        if confidence < 0.35:
            abstain = True
            abstain_reasons.append('low_confidence')
        if signal_variance > 0.08:
            abstain = True
            abstain_reasons.append('high_signal_divergence')
        if regime == 'volatile' and data_points < 5:
            abstain = True
            abstain_reasons.append('volatile_insufficient_data')

        predictions.append({
            'market_id': mid,
            'question': r['question'],
            'predicted_side': r['side'],
            'predicted_prob': r['prob'] / 100.0,
            'confidence': confidence,
            'composite_score': composite,
            'scores': {
                'statistical': round(stat_score, 4),
                'sentiment': round(sent_score, 4),
                'arbitrage': round(arb_score, 4),
                'volume': round(vol_score, 4),
                'news_volume': round(news_vol_score, 4),
            },
            'regime': regime,
            'signal_agreement': round(1.0 - signal_variance, 4),
            'abstain': abstain,
            'abstain_reasons': abstain_reasons,
            'sentiment_headlines': sent.get('matched_headlines', [])[:3],
            'url': r['url'],
            'volume': r['volume'],
            'ends_in': r['ends_in'],
            'end_date': r['end_date'],
            'kelly': arb.get('kelly_fraction', 0),
            'liquidity_factor': arb.get('liquidity_factor', 1.0),
            'checked': False,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })

    predictions.sort(key=lambda x: x['composite_score'], reverse=True)

    # Report abstention stats
    abstained = sum(1 for p in predictions if p.get('abstain'))
    if abstained:
        print(f"Predictor: {abstained}/{len(predictions)} markets flagged for abstention")

    return predictions
