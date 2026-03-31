"""
Self-improvement engine — adjusts config parameters based on prediction accuracy.
Can also request Copilot API code suggestions (max 3 per run).
Logs all changes to data/history/improvements.jsonl.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_client

_BASE = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
_CONFIG_PATH = os.path.join(_BASE, 'data', 'config.json')
_IMPROVEMENTS_PATH = os.path.join(_BASE, 'data', 'history', 'improvements.jsonl')


def _log_improvement(entry):
    """Append an improvement entry to the log file."""
    os.makedirs(os.path.dirname(_IMPROVEMENTS_PATH), exist_ok=True)
    with open(_IMPROVEMENTS_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def load_recent_improvements(n=20):
    """Load last N improvement entries for reporting."""
    if not os.path.exists(_IMPROVEMENTS_PATH):
        return []
    entries = []
    with open(_IMPROVEMENTS_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries[-n:]


def adjust_config(accuracy_metrics, config):
    """
    Adjust config parameters based on prediction accuracy.
    Returns list of changes made.
    """
    changes = []
    si = config.get('self_improve', {})
    target = si.get('accuracy_target', 0.65)
    lr = si.get('learning_rate', 0.05)
    hit_rate = accuracy_metrics.get('hit_rate', 0.0)
    total = accuracy_metrics.get('total_predictions', 0)

    if total < 5:
        # Not enough data to make adjustments
        return changes

    # 1. Adjust scoring weights based on which signals were most accurate
    # Use calibration data to identify which scores are reliable
    calibration = accuracy_metrics.get('calibration', {})
    if calibration:
        # Calculate calibration error (lower = better calibrated)
        cal_error = 0
        for bucket_str, data in calibration.items():
            expected = data.get('expected', 0.5)
            actual = data.get('actual', 0.5)
            cal_error += abs(expected - actual)
        if calibration:
            cal_error /= len(calibration)

        if cal_error > 0.20:  # poorly calibrated
            # Reduce sentiment weight (usually noisiest), increase statistical
            weights = config.get('scoring', {}).get('weights', {})
            old_sent = weights.get('sentiment', 0.20)
            new_sent = max(0.05, old_sent - lr * 0.5)
            if abs(new_sent - old_sent) > 0.001:
                weights['sentiment'] = round(new_sent, 4)
                # Redistribute to statistical
                diff = old_sent - new_sent
                weights['statistical'] = round(weights.get('statistical', 0.40) + diff, 4)
                changes.append({
                    'type': 'weight_adjustment',
                    'detail': f'sentiment {old_sent:.3f}→{new_sent:.3f}, statistical +{diff:.3f}',
                    'reason': f'calibration error {cal_error:.3f} > 0.20',
                })

    # 2. Adjust probability threshold if hit rate is too low
    if hit_rate < target - 0.10:
        scanner_cfg = config.get('scanner', {})
        old_min = scanner_cfg.get('min_prob', 70)
        new_min = min(85, old_min + 2)
        if new_min != old_min:
            scanner_cfg['min_prob'] = new_min
            changes.append({
                'type': 'threshold_adjustment',
                'detail': f'min_prob {old_min}→{new_min}',
                'reason': f'hit_rate {hit_rate:.3f} below target {target:.3f}',
            })

    # 3. Adjust volume threshold if we have too many low-quality signals
    if hit_rate < target and total > 20:
        scanner_cfg = config.get('scanner', {})
        old_vol = scanner_cfg.get('min_volume', 5000)
        new_vol = min(50000, int(old_vol * 1.1))
        if new_vol != old_vol:
            scanner_cfg['min_volume'] = new_vol
            changes.append({
                'type': 'volume_adjustment',
                'detail': f'min_volume {old_vol}→{new_vol}',
                'reason': f'hit_rate {hit_rate:.3f}, reducing noise',
            })

    # 4. If performing well, slightly relax thresholds to find more opportunities
    if hit_rate > target + 0.10:
        scanner_cfg = config.get('scanner', {})
        old_min = scanner_cfg.get('min_prob', 70)
        new_min = max(60, old_min - 1)
        if new_min != old_min:
            scanner_cfg['min_prob'] = new_min
            changes.append({
                'type': 'threshold_relaxation',
                'detail': f'min_prob {old_min}→{new_min}',
                'reason': f'hit_rate {hit_rate:.3f} exceeds target, expanding scope',
            })

    # 5. Adjust analyzer lookback windows based on Brier score
    avg_brier = accuracy_metrics.get('avg_brier_score', 0.25)
    if avg_brier > 0.30:
        analyzer_cfg = config.get('analyzer', {})
        old_windows = analyzer_cfg.get('sma_windows', [3, 7, 14])
        # Add longer window for more smoothing
        if 21 not in old_windows and len(old_windows) < 5:
            old_windows.append(21)
            old_windows.sort()
            analyzer_cfg['sma_windows'] = old_windows
            changes.append({
                'type': 'window_expansion',
                'detail': f'added SMA-21 window',
                'reason': f'Brier score {avg_brier:.3f} > 0.30, need more smoothing',
            })

    # Save config if changes were made
    if changes:
        with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        timestamp = datetime.now(timezone.utc).isoformat()
        for c in changes:
            c['timestamp'] = timestamp
            _log_improvement(c)
        print(f"Self-improvement: {len(changes)} config adjustments applied")

    return changes


def request_code_suggestions(accuracy_metrics, config, max_calls=3):
    """
    Request Copilot API suggestions when accuracy is below target.
    Uses GitHub Models API. Returns list of suggestion strings.
    Max 3 calls per run (premium request budget).
    """
    si = config.get('self_improve', {})
    target = si.get('accuracy_target', 0.65)
    hit_rate = accuracy_metrics.get('hit_rate', 0.0)
    total = accuracy_metrics.get('total_predictions', 0)

    if total < 10 or hit_rate >= target:
        return []

    token = os.environ.get('GITHUB_TOKEN', '')
    if not token:
        print("No GITHUB_TOKEN available for Copilot API calls")
        return []

    suggestions = []
    calls_made = 0

    prompts = _build_improvement_prompts(accuracy_metrics, config)

    for prompt in prompts[:max_calls]:
        if calls_made >= max_calls:
            break
        try:
            payload = {
                'messages': [
                    {'role': 'system', 'content': 'You are an expert quantitative analyst. Provide concise, actionable suggestions in JSON format with keys: suggestion, parameter, old_value, new_value, rationale.'},
                    {'role': 'user', 'content': prompt},
                ],
                'model': 'gpt-4o',
                'max_tokens': 300,
            }
            resp = http_client.post_json(
                'https://models.inference.ai.azure.com/chat/completions',
                payload,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json',
                },
                timeout=30,
            )
            calls_made += 1
            if resp and 'choices' in resp:
                content = resp['choices'][0].get('message', {}).get('content', '')
                suggestions.append(content)
                _log_improvement({
                    'type': 'copilot_suggestion',
                    'prompt_summary': prompt[:100],
                    'response_summary': content[:200],
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            print(f"Copilot API call failed: {e}")
            calls_made += 1

    if suggestions:
        print(f"Self-improvement: {len(suggestions)} Copilot suggestions received ({calls_made} API calls)")

    return suggestions


def _build_improvement_prompts(metrics, config):
    """Build strategic improvement prompts based on performance gaps."""
    prompts = []
    hit_rate = metrics.get('hit_rate', 0)
    brier = metrics.get('avg_brier_score', 0.25)
    calibration = metrics.get('calibration', {})
    weights = config.get('scoring', {}).get('weights', {})
    scanner_cfg = config.get('scanner', {})

    # 1. Strategic overview — ask for single highest-impact change
    prompts.append(
        f"Polymarket prediction system performance: hit_rate={hit_rate:.3f}, "
        f"Brier={brier:.3f}, n={metrics.get('total_predictions', 0)}. "
        f"Scoring weights: {json.dumps(weights)}. "
        f"Scanner: min_prob={scanner_cfg.get('min_prob')}, "
        f"min_volume={scanner_cfg.get('min_volume')}, "
        f"max_days={scanner_cfg.get('max_days_left')}. "
        f"Analyze which scoring signal (statistical/sentiment/arbitrage/volume) "
        f"likely contributes most to errors and suggest the single highest-impact "
        f"parameter change to improve accuracy."
    )

    # 2. Calibration analysis with readable bucket details
    if calibration:
        cal_details = []
        for bucket in sorted(calibration.keys()):
            data = calibration[bucket]
            exp = data.get('expected', 0)
            act = data.get('actual', 0)
            cnt = data.get('count', 0)
            cal_details.append(f"{exp*100:.0f}%->{act*100:.0f}% (n={cnt})")
        prompts.append(
            f"Calibration buckets: {', '.join(cal_details)}. "
            f"Current min_prob={scanner_cfg.get('min_prob')}, "
            f"max_prob={scanner_cfg.get('max_prob')}. "
            f"Which probability ranges show overconfidence or underconfidence? "
            f"Suggest specific threshold or weight adjustments for better calibration."
        )

    # 3. Systematic error pattern analysis from wrong predictions
    recent = metrics.get('recent_results', [])
    wrong = [r for r in recent if not r.get('correct', True)]
    if wrong:
        wrong_summary = json.dumps(wrong[:5], default=str)
        prompts.append(
            f"These recent predictions were wrong: {wrong_summary}. "
            f"Identify systematic error patterns: Are failures concentrated in "
            f"specific probability ranges, market types, or time horizons? "
            f"Suggest one targeted filter or parameter change to avoid similar errors."
        )

    return prompts


def run_self_improvement(accuracy_metrics, config):
    """
    Main entry point: adjust config + optionally get Copilot suggestions.
    Returns dict with changes and suggestions.
    """
    changes = adjust_config(accuracy_metrics, config)
    suggestions = request_code_suggestions(accuracy_metrics, config)
    return {
        'config_changes': changes,
        'copilot_suggestions': suggestions,
        'total_adjustments': len(changes),
    }
