"""
Arbitrage & mispricing detection for Polymarket.
Detects spread anomalies (YES+NO != 1.0), cross-market similarities,
and computes Kelly criterion for position sizing.
Uses difflib.SequenceMatcher for fuzzy question matching.
"""
import difflib
import math


def detect_spread_anomalies(scan_results, threshold=0.02):
    """
    Find markets where YES + NO probabilities deviate from 1.0.
    Returns list of dicts with spread info.
    """
    anomalies = []
    for r in scan_results:
        spread = r.get('spread', abs(r['yes_prob'] / 100 + r['no_prob'] / 100 - 1.0))
        if spread > threshold:
            anomalies.append({
                'id': r['id'],
                'question': r['question'],
                'yes_prob': r['yes_prob'],
                'no_prob': r['no_prob'],
                'spread': round(spread * 100, 2),  # as percentage
                'url': r['url'],
                'type': 'overpriced' if (r['yes_prob'] + r['no_prob']) > 100 else 'underpriced',
            })
    anomalies.sort(key=lambda x: x['spread'], reverse=True)
    return anomalies


def find_cross_market_pairs(scan_results, similarity_threshold=0.6):
    """
    Find pairs of markets with similar questions but different prices.
    Uses SequenceMatcher for fuzzy matching.
    Returns list of pair dicts.
    """
    pairs = []
    seen = set()
    for i, a in enumerate(scan_results):
        for j, b in enumerate(scan_results):
            if i >= j:
                continue
            pair_key = (a['id'], b['id'])
            if pair_key in seen:
                continue
            seen.add(pair_key)

            sim = difflib.SequenceMatcher(
                None, a['question'].lower(), b['question'].lower()
            ).ratio()

            if sim >= similarity_threshold:
                price_diff = abs(a['prob'] - b['prob'])
                if price_diff > 3.0:  # at least 3% difference to be interesting
                    pairs.append({
                        'market_a': {'id': a['id'], 'question': a['question'],
                                     'side': a['side'], 'prob': a['prob'], 'url': a['url']},
                        'market_b': {'id': b['id'], 'question': b['question'],
                                     'side': b['side'], 'prob': b['prob'], 'url': b['url']},
                        'similarity': round(sim, 3),
                        'price_diff': round(price_diff, 2),
                    })

    pairs.sort(key=lambda x: x['price_diff'], reverse=True)
    return pairs


def kelly_fraction(prob, odds=None):
    """
    Kelly criterion for optimal bet sizing.
    prob: estimated true probability (0-1)
    odds: decimal odds (payout per unit bet). If None, derived from market price.
    Returns fraction of bankroll to bet (0-1, capped at 0.25 for safety).
    """
    if odds is None:
        if prob <= 0 or prob >= 1:
            return 0.0
        odds = 1.0 / prob  # fair odds from market price

    # Kelly: (bp - q) / b where b=odds-1, p=prob, q=1-p
    b = odds - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - prob
    fraction = (b * prob - q) / b
    # Cap at 25% and floor at 0
    return max(0.0, min(0.25, fraction))


def compute_arbitrage_scores(scan_results):
    """
    Compute an arbitrage/mispricing score for each market.
    Returns dict: market_id → {arb_score, spread, kelly, type}.
    """
    scores = {}
    anomalies = detect_spread_anomalies(scan_results, threshold=0.005)
    anomaly_map = {a['id']: a for a in anomalies}

    for r in scan_results:
        mid = r['id']
        prob = r['prob'] / 100.0  # convert percentage to 0-1

        spread = r.get('spread', 0)
        kelly_f = kelly_fraction(prob)

        # Arbitrage score: combination of spread anomaly + Kelly edge
        spread_score = min(1.0, spread * 20)  # 5% spread → score 1.0
        kelly_score = min(1.0, kelly_f * 4)   # 25% kelly → score 1.0

        arb_score = round(spread_score * 0.5 + kelly_score * 0.5, 4)

        scores[mid] = {
            'arb_score': arb_score,
            'spread_pct': round(spread * 100, 2),
            'kelly_fraction': round(kelly_f, 4),
            'has_anomaly': mid in anomaly_map,
        }

    return scores
