"""
Polymarket market scanner.
Fetches active markets from Gamma API, filters by configurable criteria,
enriches with real-time CLOB midpoint prices.
Stdlib only — uses http_client (urllib wrapper).
"""
import json
import re
import os
import sys
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

# Allow imports when run from scripts/ directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_client

GAMMA_API = "https://gamma-api.polymarket.com/markets"
CLOB_API = "https://clob.polymarket.com/midpoint"

# --- Date extraction from question text ---
_MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}
_DATE_IN_Q_RE = re.compile(
    r'\b(?:by|before|until|through)\s+'
    r'(?P<month>' + '|'.join(_MONTH_MAP.keys()) + r')'
    r'\s+(?P<day>\d{1,2})'
    r'(?:[,\s]+(?P<year>\d{4}))?',
    re.IGNORECASE
)


def _extract_question_date(question, reference_year=None):
    if not question:
        return None
    if reference_year is None:
        reference_year = datetime.now(timezone.utc).year
    dates = []
    for m in _DATE_IN_Q_RE.finditer(question):
        month = _MONTH_MAP.get(m.group('month').lower())
        day = int(m.group('day'))
        year = int(m.group('year')) if m.group('year') else reference_year
        try:
            dt = datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc)
            if dt < datetime.now(timezone.utc) and not m.group('year'):
                dt = datetime(year + 1, month, day, 23, 59, 59, tzinfo=timezone.utc)
            dates.append(dt)
        except ValueError:
            continue
    return max(dates) if dates else None


def _parse_end_date(end_date_str):
    if not end_date_str:
        return None
    try:
        cleaned = end_date_str.replace('Z', '+00:00')
        return datetime.fromisoformat(cleaned)
    except (ValueError, TypeError):
        return None


def _build_url(market):
    events = market.get('events')
    if events and isinstance(events, list) and len(events) > 0:
        slug = events[0].get('slug', '')
        if slug:
            return f"https://polymarket.com/event/{slug}"
    return f"https://polymarket.com/event/{market.get('slug', '')}"


def _human_remaining(td):
    total = int(td.total_seconds())
    if total <= 0:
        return "sona erdi"
    d, rem = divmod(total, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    parts = []
    if d: parts.append(f"{d}g")
    if h: parts.append(f"{h}s")
    if m or not parts: parts.append(f"{m}d")
    return " ".join(parts)


def _fetch_clob_midpoint(token_id, timeout=5):
    try:
        data = http_client.get(CLOB_API, params={'token_id': token_id}, timeout=timeout)
        return float(data.get('mid', 0))
    except Exception:
        return None


def _fetch_clob_prices(yes_token, no_token, timeout=5):
    with ThreadPoolExecutor(max_workers=2) as ex:
        fy = ex.submit(_fetch_clob_midpoint, yes_token, timeout)
        fn = ex.submit(_fetch_clob_midpoint, no_token, timeout)
        return fy.result(), fn.result()


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data', 'config.json')
    config_path = os.path.normpath(config_path)
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def scan_markets(config=None):
    """
    Scan Polymarket for opportunities matching config criteria.
    Returns list of dicts with market data + prices.
    """
    if config is None:
        config = load_config()

    sc = config['scanner']
    min_volume = sc['min_volume']
    max_days = sc['max_days_left']
    min_prob = sc['min_prob']
    max_prob = sc['max_prob']
    side = sc['side']
    batch_size = sc.get('api_batch_size', 500)
    clob_timeout = sc.get('clob_timeout', 5)
    clob_workers = sc.get('clob_workers', 10)

    # Build exclude regex from config
    patterns = config.get('exclude_patterns', [])
    exclude_re = re.compile('|'.join(patterns), re.IGNORECASE) if patterns else None
    exclude_slugs = tuple(config.get('exclude_slug_prefixes', []))

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=max_days)

    # --- Fetch all active markets ---
    markets = []
    offset = 0
    while True:
        params = {"active": "true", "closed": "false", "limit": batch_size, "offset": offset}
        try:
            batch = http_client.get(GAMMA_API, params=params, timeout=15)
        except Exception as e:
            print(f"API error at offset {offset}: {e}", file=sys.stderr)
            break
        if not batch:
            break
        markets.extend(batch)
        if len(batch) < batch_size:
            break
        offset += batch_size

    print(f"Fetched {len(markets)} active markets.")

    # --- Pre-filter ---
    tolerance = 0.05
    pre_candidates = []

    for m in markets:
        # Noise filter
        question = m.get('question', '')
        slug = m.get('slug', '')
        if exclude_re and exclude_re.search(question):
            continue
        if slug.startswith(exclude_slugs):
            continue

        # Volume check
        volume = float(m.get('volume', 0))
        if volume < min_volume:
            continue

        # Time check
        end_date = _parse_end_date(m.get('endDate'))
        if end_date is None:
            continue
        q_date = _extract_question_date(question)
        if q_date and q_date > end_date:
            end_date = q_date
        if not (now < end_date <= deadline):
            continue

        # Price pre-filter (Gamma prices, with tolerance)
        prices_raw = m.get('outcomePrices')
        if not prices_raw:
            continue
        try:
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
        except (json.JSONDecodeError, TypeError):
            continue
        if len(prices) < 2:
            continue

        yes_prob = float(prices[0])
        no_prob = float(prices[1])

        yes_ok = (min_prob - tolerance) <= yes_prob <= (max_prob + tolerance)
        no_ok = (min_prob - tolerance) <= no_prob <= (max_prob + tolerance)

        if side == 'yes' and not yes_ok:
            continue
        elif side == 'no' and not no_ok:
            continue
        elif side == 'both' and not (yes_ok or no_ok):
            continue

        # CLOB token IDs
        clob_raw = m.get('clobTokenIds')
        if not clob_raw:
            continue
        try:
            clob_ids = json.loads(clob_raw) if isinstance(clob_raw, str) else clob_raw
        except (json.JSONDecodeError, TypeError):
            continue
        if len(clob_ids) < 2:
            continue

        pre_candidates.append({
            'market': m,
            'end_date': end_date,
            'yes_token': clob_ids[0],
            'no_token': clob_ids[1],
        })

    print(f"{len(pre_candidates)} candidates pass pre-filter. Fetching CLOB prices...")

    # --- Enrich with CLOB midpoint prices ---
    def _enrich(item):
        y, n = _fetch_clob_prices(item['yes_token'], item['no_token'], clob_timeout)
        item['yes_mid'] = y
        item['no_mid'] = n
        return item

    with ThreadPoolExecutor(max_workers=clob_workers) as ex:
        pre_candidates = list(ex.map(_enrich, pre_candidates))

    # --- Final filter with real prices ---
    results = []
    for item in pre_candidates:
        m = item['market']
        end_date = item['end_date']
        yes_mid = item['yes_mid']
        no_mid = item['no_mid']

        if yes_mid is not None and no_mid is not None:
            yes_prob = yes_mid
            no_prob = no_mid
        else:
            prices_raw = m.get('outcomePrices')
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            yes_prob = float(prices[0])
            no_prob = float(prices[1])

        candidates = []
        if side in ('yes', 'both') and min_prob <= yes_prob <= max_prob:
            candidates.append(('YES', round(yes_prob * 100, 2)))
        if side in ('no', 'both') and min_prob <= no_prob <= max_prob:
            candidates.append(('NO', round(no_prob * 100, 2)))

        for side_label, prob in candidates:
            condition_id = m.get('conditionId', m.get('id', ''))
            results.append({
                "id": condition_id,
                "question": m.get('question', ''),
                "slug": m.get('slug', ''),
                "side": side_label,
                "prob": prob,
                "yes_prob": round(yes_prob * 100, 2),
                "no_prob": round(no_prob * 100, 2),
                "volume": float(m.get('volume', 0)),
                "volume_fmt": f"{float(m.get('volume', 0)):,.0f}",
                "end_date": end_date.strftime('%d %b %Y'),
                "end_date_iso": end_date.isoformat(),
                "ends_in": _human_remaining(end_date - now),
                "url": _build_url(m),
                "spread": round(abs(yes_prob + no_prob - 1.0), 4),
                "yes_token": item['yes_token'],
                "no_token": item['no_token'],
            })

    results.sort(key=lambda x: x['prob'], reverse=True)
    print(f"Found {len(results)} opportunities.")
    return results


if __name__ == '__main__':
    results = scan_markets()
    for r in results:
        print(f"[{r['side']}] {r['prob']}% — {r['question']}")
        print(f"  Vol: ${r['volume_fmt']} | Ends: {r['end_date']} ({r['ends_in']})")
        print(f"  {r['url']}")
        print()
