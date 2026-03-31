"""
Time series & statistical analysis for Polymarket price data.
Uses only statistics + math from stdlib.
Maintains price history in data/history/ as JSON files.
"""
import json
import math
import os
import statistics
from datetime import datetime, timezone


def _history_dir():
    base = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data', 'history')
    base = os.path.normpath(base)
    os.makedirs(base, exist_ok=True)
    return base


def _signal_accuracy_file():
    return os.path.join(_history_dir(), 'signal_accuracy.json')


def load_signal_accuracy():
    """Load per-signal accuracy tracking data for dynamic weight adjustment."""
    path = _signal_accuracy_file()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'statistical': {'correct': 0, 'total': 0},
        'sentiment': {'correct': 0, 'total': 0},
        'arbitrage': {'correct': 0, 'total': 0},
        'volume': {'correct': 0, 'total': 0},
    }


def save_signal_accuracy(data):
    path = _signal_accuracy_file()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_signal_accuracy(predictions_with_outcomes):
    """
    Track which signals were correct/wrong for dynamic weight adjustment.
    Inspired by Greedy-Weighted Ensemble paper: dynamically allocate model
    weights based on empirical predictive performance.
    """
    acc = load_signal_accuracy()

    for p in predictions_with_outcomes:
        if not p.get('checked') or p.get('correct') is None:
            continue
        scores = p.get('scores', {})
        is_correct = p['correct']

        for signal_name in ['statistical', 'sentiment', 'arbitrage', 'volume']:
            signal_val = scores.get(signal_name, 0.5)
            # A signal "agreed" with the prediction if it's above 0.5
            signal_agreed = signal_val > 0.5
            if signal_agreed == is_correct:
                acc[signal_name]['correct'] = acc[signal_name].get('correct', 0) + 1
            acc[signal_name]['total'] = acc[signal_name].get('total', 0) + 1

    save_signal_accuracy(acc)
    return acc


def compute_dynamic_weights(config):
    """
    Compute scoring weights dynamically based on per-signal accuracy history.
    Greedy-Weighted Ensemble approach: signals that have been more accurate
    historically get higher weight. Falls back to static config weights
    when not enough data exists.
    """
    acc = load_signal_accuracy()
    static_weights = config.get('scoring', {}).get('weights', {})

    min_samples = 20  # need at least this many checked predictions
    total_checked = min(d.get('total', 0) for d in acc.values())
    if total_checked < min_samples:
        return static_weights  # not enough data for dynamic weights

    # Compute accuracy rate per signal
    rates = {}
    for signal_name, data in acc.items():
        total = data.get('total', 0)
        correct = data.get('correct', 0)
        if total > 0:
            rates[signal_name] = correct / total
        else:
            rates[signal_name] = 0.5  # neutral

    # Softmax-like normalization to get weights from accuracy rates
    # Higher accuracy → higher weight, but bounded to prevent any signal
    # from dominating completely
    min_weight = 0.05  # no signal drops below 5%
    max_weight = 0.60  # no signal exceeds 60%
    total_rate = sum(rates.values())
    if total_rate == 0:
        return static_weights

    dynamic = {}
    for signal_name, rate in rates.items():
        raw = rate / total_rate
        dynamic[signal_name] = max(min_weight, min(max_weight, round(raw, 4)))

    # Renormalize to sum to 1.0
    total_w = sum(dynamic.values())
    for k in dynamic:
        dynamic[k] = round(dynamic[k] / total_w, 4)

    return dynamic


def _history_dir():
    base = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data', 'history')
    base = os.path.normpath(base)
    os.makedirs(base, exist_ok=True)
    return base


def _prices_file():
    return os.path.join(_history_dir(), 'price_history.json')


def load_price_history():
    path = _prices_file()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_price_history(history):
    path = _prices_file()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=1)


def record_prices(scan_results):
    """Append today's prices for each market into history."""
    history = load_price_history()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    for r in scan_results:
        mid = r['id']
        if mid not in history:
            history[mid] = {'question': r['question'], 'prices': []}
        # Avoid duplicate entries for same day
        existing_dates = {p['date'] for p in history[mid]['prices']}
        if today not in existing_dates:
            history[mid]['prices'].append({
                'date': today,
                'yes': r['yes_prob'],
                'no': r['no_prob'],
                'volume': r['volume'],
            })

    save_price_history(history)
    return history


def _get_series(history_entry, field='yes'):
    """Extract a time-ordered list of float values from price history."""
    prices = history_entry.get('prices', [])
    prices_sorted = sorted(prices, key=lambda p: p['date'])
    return [p[field] for p in prices_sorted]


def sma(series, window):
    """Simple Moving Average over the last *window* values."""
    if len(series) < window:
        return None
    return statistics.mean(series[-window:])


def volatility(series, window):
    """Standard deviation of last *window* values (population)."""
    if len(series) < window or window < 2:
        return None
    return statistics.stdev(series[-window:])


def momentum(series, window):
    """(last - N_ago) / N_ago as a fraction."""
    if len(series) < window + 1:
        return None
    old = series[-(window + 1)]
    if old == 0:
        return None
    return (series[-1] - old) / old


def zscore(series, window):
    """Z-score of the latest value relative to last *window* values."""
    if len(series) < window or window < 2:
        return None
    subset = series[-window:]
    mean = statistics.mean(subset)
    sd = statistics.stdev(subset)
    if sd == 0:
        return 0.0
    return (series[-1] - mean) / sd


def mean_reversion_score(series, window):
    """How far current price deviates from SMA, normalised by volatility.
    Positive → above average (potential overpriced).
    Negative → below average (potential underpriced).
    """
    avg = sma(series, window)
    vol = volatility(series, window)
    if avg is None or vol is None or vol == 0:
        return None
    return (series[-1] - avg) / vol


def detect_regime(series, window=7):
    """
    Detect volatility regime: calm, normal, or volatile.
    Inspired by "Quantitative Financial Modeling" paper — uses clustering-like
    approach to identify market conditions. Volatile regimes warrant higher
    caution (lower position size, higher confidence threshold).
    """
    if len(series) < window + 1:
        return 'unknown', 0.0

    # Compute rolling returns
    returns = []
    for i in range(1, len(series)):
        if series[i - 1] != 0:
            returns.append((series[i] - series[i - 1]) / series[i - 1])

    if len(returns) < window:
        return 'unknown', 0.0

    recent_returns = returns[-window:]
    vol = statistics.stdev(recent_returns) if len(recent_returns) >= 2 else 0

    # Classify based on volatility thresholds
    if vol < 0.02:
        return 'calm', vol
    elif vol < 0.08:
        return 'normal', vol
    else:
        return 'volatile', vol


def trend_strength(series, window=7):
    """
    Measure directional consistency of recent price moves.
    Returns value between -1 (strong downtrend) and +1 (strong uptrend).
    """
    if len(series) < window + 1:
        return 0.0
    recent = series[-(window + 1):]
    ups = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i - 1])
    downs = sum(1 for i in range(1, len(recent)) if recent[i] < recent[i - 1])
    total = ups + downs
    if total == 0:
        return 0.0
    return (ups - downs) / total


def analyze_market(history_entry, config=None):
    """
    Compute all statistical indicators for a single market.
    Returns a dict of metrics, or empty dict if not enough data.
    """
    if config is None:
        config = {}
    ac = config.get('analyzer', {})
    sma_windows = ac.get('sma_windows', [3, 7, 14])
    vol_window = ac.get('volatility_window', 7)
    mom_window = ac.get('momentum_window', 3)
    z_window = ac.get('zscore_window', 14)

    yes_series = _get_series(history_entry, 'yes')
    no_series = _get_series(history_entry, 'no')

    if len(yes_series) < 2:
        return {}

    metrics = {
        'data_points': len(yes_series),
        'latest_yes': yes_series[-1] if yes_series else None,
        'latest_no': no_series[-1] if no_series else None,
    }

    # SMA for each window
    for w in sma_windows:
        metrics[f'sma_{w}_yes'] = sma(yes_series, w)
        metrics[f'sma_{w}_no'] = sma(no_series, w)

    metrics['volatility_yes'] = volatility(yes_series, vol_window)
    metrics['volatility_no'] = volatility(no_series, vol_window)
    metrics['momentum_yes'] = momentum(yes_series, mom_window)
    metrics['momentum_no'] = momentum(no_series, mom_window)
    metrics['zscore_yes'] = zscore(yes_series, z_window)
    metrics['zscore_no'] = zscore(no_series, z_window)
    metrics['mean_rev_yes'] = mean_reversion_score(yes_series, vol_window)
    metrics['mean_rev_no'] = mean_reversion_score(no_series, vol_window)

    # Regime detection (from "Quantitative Financial Modeling" paper)
    regime, regime_vol = detect_regime(yes_series, vol_window)
    metrics['regime'] = regime
    metrics['regime_volatility'] = round(regime_vol, 6) if regime_vol else 0

    # Trend strength
    metrics['trend_yes'] = round(trend_strength(yes_series, vol_window), 4)
    metrics['trend_no'] = round(trend_strength(no_series, vol_window), 4)

    # Composite statistical score: 0-1 (higher = more attractive)
    vol_y = metrics.get('volatility_yes')
    mr_y = metrics.get('mean_rev_yes')
    vol_n = metrics.get('volatility_no')
    mr_n = metrics.get('mean_rev_no')

    scores = {}
    for side, vol_val, mr_val in [('yes', vol_y, mr_y), ('no', vol_n, mr_n)]:
        if vol_val is not None and mr_val is not None:
            # Lower vol → higher score; negative mean_rev → underpriced → higher score
            vol_score = max(0, 1.0 - vol_val / 50.0)  # normalise vol (0-50% range)
            mr_score = max(0, min(1, 0.5 - mr_val * 0.2))  # negative mr → higher

            # Regime adjustment: in volatile regimes, reduce stat confidence
            regime_penalty = 1.0
            if regime == 'volatile':
                regime_penalty = 0.8  # 20% penalty in volatile markets
            elif regime == 'calm':
                regime_penalty = 1.1  # 10% bonus in calm markets

            raw_score = vol_score * 0.6 + mr_score * 0.4
            scores[f'stat_score_{side}'] = round(min(1.0, raw_score * regime_penalty), 4)
        else:
            scores[f'stat_score_{side}'] = 0.5  # neutral default
    metrics.update(scores)

    return metrics


def analyze_all(scan_results, config=None):
    """
    Analyze all scanned markets. Returns dict: market_id → metrics.
    Also records today's prices into history.
    """
    history = record_prices(scan_results)

    analysis = {}
    for r in scan_results:
        mid = r['id']
        entry = history.get(mid, {})
        metrics = analyze_market(entry, config)
        analysis[mid] = metrics

    return analysis
