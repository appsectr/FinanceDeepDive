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

    # Composite statistical score: 0-1 (higher = more attractive)
    # Based on: low volatility = safer, positive mean reversion = potential
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
            scores[f'stat_score_{side}'] = round((vol_score * 0.6 + mr_score * 0.4), 4)
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
