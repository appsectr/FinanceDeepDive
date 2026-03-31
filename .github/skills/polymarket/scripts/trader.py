"""
Auto-trading engine for Polymarket — places bets based on predictions.
DISABLED by default: config.trading.enabled must be True.
Requires POLYMARKET_API_KEY and POLYMARKET_API_SECRET env vars.

Safety features:
  - Daily spending cap
  - Per-bet max USD
  - Minimum Kelly threshold filter
  - Minimum composite score filter
  - Dry-run mode (logs orders without executing)
  - Position tracking to avoid double-betting
  - All trades logged to data/history/trades.jsonl
"""
import json
import os
import sys
import hashlib
import hmac
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_client

_BASE = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
_TRADES_LOG = os.path.join(_BASE, 'data', 'history', 'trades.jsonl')
_POSITIONS_FILE = os.path.join(_BASE, 'data', 'history', 'positions.json')

CLOB_BASE = 'https://clob.polymarket.com'


# ---------------------------------------------------------------------------
# Position tracking
# ---------------------------------------------------------------------------

def _load_positions():
    """Load current open positions."""
    if not os.path.exists(_POSITIONS_FILE):
        return {}
    with open(_POSITIONS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_positions(positions):
    """Save current positions to disk."""
    os.makedirs(os.path.dirname(_POSITIONS_FILE), exist_ok=True)
    with open(_POSITIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=2)


def _log_trade(entry):
    """Append a trade entry to the log file."""
    os.makedirs(os.path.dirname(_TRADES_LOG), exist_ok=True)
    with open(_TRADES_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def load_trade_history(n=50):
    """Load last N trade log entries."""
    if not os.path.exists(_TRADES_LOG):
        return []
    entries = []
    with open(_TRADES_LOG, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries[-n:]


# ---------------------------------------------------------------------------
# Daily spending tracker
# ---------------------------------------------------------------------------

def _get_daily_spent():
    """Calculate total USD spent today from trade log."""
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    total = 0.0
    history = load_trade_history(200)
    for t in history:
        if t.get('timestamp', '').startswith(today) and t.get('status') == 'executed':
            total += t.get('amount_usd', 0.0)
    return total


# ---------------------------------------------------------------------------
# CLOB API interaction
# ---------------------------------------------------------------------------

def _clob_headers(api_key, api_secret, method, path, body=''):
    """
    Build authentication headers for the Polymarket CLOB API.
    Uses HMAC-SHA256 signature.
    """
    timestamp = str(int(time.time()))
    message = timestamp + method.upper() + path + body
    signature = hmac.new(
        api_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    return {
        'POLY-API-KEY': api_key,
        'POLY-SIGNATURE': signature,
        'POLY-TIMESTAMP': timestamp,
        'Content-Type': 'application/json',
    }


def _place_order(token_id, side, price, size, api_key, api_secret):
    """
    Place a limit order on the Polymarket CLOB.
    Returns order response dict or None on failure.

    Parameters:
        token_id: The condition token ID for the market outcome
        side:     'BUY' or 'SELL'
        price:    Price per share (0.01 - 0.99)
        size:     Number of shares
        api_key:  CLOB API key
        api_secret: CLOB API secret
    """
    path = '/order'
    order_payload = {
        'tokenID': token_id,
        'side': side,
        'price': str(price),
        'size': str(size),
        'type': 'GTC',  # Good Till Cancel
    }
    body = json.dumps(order_payload, separators=(',', ':'))
    headers = _clob_headers(api_key, api_secret, 'POST', path, body)

    try:
        resp = http_client.post_json(
            CLOB_BASE + path,
            order_payload,
            headers=headers,
            timeout=15,
        )
        return resp
    except Exception as e:
        print(f"  Order placement failed: {e}")
        return None


def _get_token_id(market_id, side):
    """
    Fetch the condition token ID for a market + side (YES/NO).
    Uses the Gamma API market endpoint.
    """
    try:
        data = http_client.get(
            f'https://gamma-api.polymarket.com/markets/{market_id}',
            timeout=10,
        )
        if not data:
            return None
        tokens = data.get('clobTokenIds', '')
        if isinstance(tokens, str):
            tokens = json.loads(tokens) if tokens.startswith('[') else [tokens]
        # tokens[0] = YES token, tokens[1] = NO token
        if side.upper() == 'YES' and len(tokens) > 0:
            return tokens[0]
        elif side.upper() == 'NO' and len(tokens) > 1:
            return tokens[1]
        return tokens[0] if tokens else None
    except Exception as e:
        print(f"  Failed to get token ID for {market_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# Trade execution engine
# ---------------------------------------------------------------------------

def _filter_predictions(predictions, config):
    """
    Filter predictions that meet trading criteria.
    Returns list of tradeable predictions.
    """
    tc = config.get('trading', {})
    min_kelly = tc.get('min_kelly', 0.05)
    min_composite = tc.get('min_composite_score', 0.60)
    max_per_bet = tc.get('max_per_bet_usd', 10.0)

    positions = _load_positions()
    tradeable = []

    for pred in predictions:
        mid = pred.get('market_id', '')

        # Skip if already positioned
        if mid in positions:
            continue

        # Kelly threshold
        kelly = pred.get('kelly', 0)
        if kelly < min_kelly:
            continue

        # Composite score threshold
        composite = pred.get('composite_score', 0)
        if composite < min_composite:
            continue

        # Must have a meaningful probability edge
        prob = pred.get('predicted_prob', 0.5)
        if prob < 0.05 or prob > 0.95:
            continue

        tradeable.append(pred)

    return tradeable


def execute_trades(predictions, config):
    """
    Main entry point: evaluate predictions and execute qualifying trades.

    Returns dict with:
        trades_attempted: int
        trades_executed: int
        trades_skipped: int
        total_usd_spent: float
        details: list of trade details
    """
    tc = config.get('trading', {})

    # Guard: trading must be explicitly enabled
    if not tc.get('enabled', False):
        print("  Trading is DISABLED (config.trading.enabled = false)")
        return {
            'trades_attempted': 0,
            'trades_executed': 0,
            'trades_skipped': 0,
            'total_usd_spent': 0.0,
            'details': [],
        }

    dry_run = tc.get('dry_run', True)
    max_daily = tc.get('max_daily_usd', 50.0)
    max_per_bet = tc.get('max_per_bet_usd', 10.0)

    # Check API credentials
    api_key = os.environ.get('POLYMARKET_API_KEY', '')
    api_secret = os.environ.get('POLYMARKET_API_SECRET', '')
    if not dry_run and (not api_key or not api_secret):
        print("  ERROR: POLYMARKET_API_KEY or POLYMARKET_API_SECRET not set")
        return {
            'trades_attempted': 0,
            'trades_executed': 0,
            'trades_skipped': 0,
            'total_usd_spent': 0.0,
            'details': [],
            'error': 'Missing API credentials',
        }

    # Filter predictions
    tradeable = _filter_predictions(predictions, config)
    if not tradeable:
        print("  No predictions meet trading criteria")
        return {
            'trades_attempted': 0,
            'trades_executed': 0,
            'trades_skipped': len(predictions),
            'total_usd_spent': 0.0,
            'details': [],
        }

    daily_spent = _get_daily_spent()
    positions = _load_positions()
    results = []
    executed = 0
    skipped = 0

    for pred in tradeable:
        # Daily budget check
        if daily_spent >= max_daily:
            print(f"  Daily budget exhausted (${daily_spent:.2f}/${max_daily:.2f})")
            skipped += len(tradeable) - (executed + skipped)
            break

        mid = pred['market_id']
        side = pred['predicted_side']
        prob = pred['predicted_prob']
        kelly = pred.get('kelly', 0)
        composite = pred['composite_score']

        # Calculate bet size: Kelly fraction * max_per_bet, capped
        bet_usd = min(
            kelly * max_per_bet,
            max_per_bet,
            max_daily - daily_spent,
        )
        bet_usd = round(bet_usd, 2)

        if bet_usd < 0.50:
            skipped += 1
            continue

        # Price = predicted probability (we're buying at this price or better)
        price = round(prob, 2)
        # Size = bet_usd / price (number of shares)
        size = round(bet_usd / price, 2) if price > 0 else 0

        trade_entry = {
            'market_id': mid,
            'question': pred.get('question', ''),
            'side': side,
            'price': price,
            'size': size,
            'amount_usd': bet_usd,
            'kelly': kelly,
            'composite_score': composite,
            'dry_run': dry_run,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

        if dry_run:
            trade_entry['status'] = 'dry_run'
            print(f"  [DRY RUN] {side} ${bet_usd:.2f} @ {price:.2f} — {pred.get('question', '')[:60]}")
        else:
            # Resolve token ID
            token_id = _get_token_id(mid, side)
            if not token_id:
                trade_entry['status'] = 'failed'
                trade_entry['error'] = 'Could not resolve token ID'
                skipped += 1
                _log_trade(trade_entry)
                results.append(trade_entry)
                continue

            # Place the order
            resp = _place_order(token_id, 'BUY', price, size, api_key, api_secret)
            if resp and resp.get('orderID'):
                trade_entry['status'] = 'executed'
                trade_entry['order_id'] = resp['orderID']
                daily_spent += bet_usd
                executed += 1

                # Track position
                positions[mid] = {
                    'side': side,
                    'price': price,
                    'size': size,
                    'amount_usd': bet_usd,
                    'order_id': resp['orderID'],
                    'timestamp': trade_entry['timestamp'],
                }
            else:
                trade_entry['status'] = 'failed'
                trade_entry['error'] = str(resp) if resp else 'No response'
                skipped += 1

        _log_trade(trade_entry)
        results.append(trade_entry)

    # Save updated positions
    _save_positions(positions)

    total_spent = sum(t.get('amount_usd', 0) for t in results if t.get('status') == 'executed')
    dry_count = sum(1 for t in results if t.get('status') == 'dry_run')

    summary = {
        'trades_attempted': len(tradeable),
        'trades_executed': executed,
        'trades_dry_run': dry_count,
        'trades_skipped': skipped,
        'total_usd_spent': round(total_spent, 2),
        'details': results,
    }

    action = "DRY RUN" if dry_run else "LIVE"
    print(f"  [{action}] {len(results)} trades processed, ${total_spent:.2f} spent")

    return summary
