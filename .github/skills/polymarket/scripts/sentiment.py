"""
Rule-based sentiment analysis via RSS news feeds.
Uses urllib + xml.etree.ElementTree — no 3rd party deps.
Matches news headlines to market questions with regex,
scores each market on a -1.0 to +1.0 sentiment scale.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_client

# --- Sentiment lexicon (English, politics/policy-heavy) ---
POSITIVE_WORDS = {
    'approve', 'approved', 'approval', 'pass', 'passed', 'passes', 'sign', 'signed',
    'win', 'wins', 'won', 'victory', 'succeed', 'success', 'successful', 'gain',
    'boost', 'surge', 'soar', 'rise', 'rising', 'increase', 'support', 'endorse',
    'agree', 'agreement', 'deal', 'progress', 'advance', 'rally', 'confident',
    'optimistic', 'strong', 'strengthen', 'recover', 'recovery', 'reform',
    'breakthrough', 'milestone', 'achieve', 'achievement', 'lead', 'leading',
    'confirm', 'confirmed', 'ratify', 'ratified', 'uphold', 'upheld',
    'bipartisan', 'unanimous', 'landmark', 'historic',
}

NEGATIVE_WORDS = {
    'reject', 'rejected', 'deny', 'denied', 'block', 'blocked', 'fail', 'failed',
    'failure', 'lose', 'lost', 'defeat', 'veto', 'vetoed', 'oppose', 'opposed',
    'opposition', 'crisis', 'crash', 'collapse', 'decline', 'drop', 'fall',
    'falling', 'risk', 'threat', 'warn', 'warning', 'fear', 'concern',
    'scandal', 'investigate', 'investigation', 'indict', 'indicted', 'impeach',
    'impeachment', 'resign', 'resignation', 'suspend', 'sanction', 'sanctions',
    'tariff', 'tariffs', 'shutdown', 'deadlock', 'stall', 'stalled',
    'withdraw', 'withdrawal', 'delay', 'delayed', 'uncertain', 'uncertainty',
    'controversial', 'dispute', 'conflict', 'tension',
}

# Multiplier words that amplify sentiment
AMPLIFIERS = {'very', 'extremely', 'strongly', 'significantly', 'sharply', 'dramatically'}
NEGATORS = {'not', 'no', 'never', 'neither', 'nor', "don't", "doesn't", "didn't", "won't", "can't"}


def _parse_rss(xml_text):
    """Parse RSS/Atom feed, return list of {'title': str, 'published': str}."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    # RSS 2.0
    for item in root.iter('item'):
        title_el = item.find('title')
        pub_el = item.find('pubDate')
        if title_el is not None and title_el.text:
            items.append({
                'title': title_el.text.strip(),
                'published': pub_el.text.strip() if pub_el is not None and pub_el.text else '',
            })

    # Atom fallback
    if not items:
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        for entry in root.iter('{http://www.w3.org/2005/Atom}entry'):
            title_el = entry.find('atom:title', ns) or entry.find('{http://www.w3.org/2005/Atom}title')
            if title_el is not None and title_el.text:
                items.append({'title': title_el.text.strip(), 'published': ''})

    return items


def fetch_news(config=None):
    """Fetch all configured RSS feeds, return flat list of headline dicts."""
    if config is None:
        config = {}
    feeds = config.get('sentiment', {}).get('rss_feeds', [
        'https://news.google.com/rss/search?q=politics&hl=en-US&gl=US&ceid=US:en',
    ])

    all_headlines = []
    for url in feeds:
        try:
            xml = http_client.get_text(url, timeout=10)
            items = _parse_rss(xml)
            all_headlines.extend(items)
        except Exception:
            continue

    return all_headlines


def _extract_keywords(question):
    """Extract meaningful keywords from a market question for matching."""
    # Remove common stop words and short words
    stop = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'will',
            'would', 'could', 'should', 'may', 'might', 'can', 'do', 'does', 'did',
            'has', 'have', 'had', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'this', 'that', 'it', 'its', 'or', 'and', 'but', 'if',
            'than', 'then', 'so', 'as', 'up', 'out', 'about', 'into', 'over',
            'after', 'before', 'between', 'under', 'again', 'there', 'here', 'when',
            'where', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
            'most', 'other', 'some', 'such', 'no', 'not', 'only', 'own', 'same',
            'what', 'which', 'who', 'whom'}
    words = re.findall(r'[a-zA-Z]+', question.lower())
    return {w for w in words if w not in stop and len(w) > 2}


def _score_headline(headline_text):
    """Score a single headline: -1.0 to +1.0."""
    words = headline_text.lower().split()
    pos = 0
    neg = 0
    negate = False

    for i, word in enumerate(words):
        clean = re.sub(r'[^a-z]', '', word)
        if clean in NEGATORS:
            negate = True
            continue
        if clean in AMPLIFIERS:
            continue

        amplify = 1.5 if (i > 0 and re.sub(r'[^a-z]', '', words[i-1]) in AMPLIFIERS) else 1.0

        if clean in POSITIVE_WORDS:
            if negate:
                neg += amplify
            else:
                pos += amplify
            negate = False
        elif clean in NEGATIVE_WORDS:
            if negate:
                pos += amplify
            else:
                neg += amplify
            negate = False
        else:
            negate = False

    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total


def analyze_sentiment(scan_results, config=None):
    """
    For each scanned market, find related news headlines and compute sentiment.
    Returns dict: market_id → {score, matched_headlines, headline_count}.
    """
    headlines = fetch_news(config)
    print(f"Fetched {len(headlines)} news headlines for sentiment analysis.")

    sentiment_data = {}

    for r in scan_results:
        mid = r['id']
        keywords = _extract_keywords(r['question'])
        if not keywords:
            sentiment_data[mid] = {'score': 0.0, 'matched_headlines': [], 'headline_count': 0}
            continue

        matched = []
        for h in headlines:
            htitle = h['title'].lower()
            # Match if at least 2 keywords appear in headline (or 1 if it's a proper noun / long keyword)
            matching_kws = {kw for kw in keywords if kw in htitle}
            threshold = 1 if any(len(kw) > 5 for kw in matching_kws) else 2
            if len(matching_kws) >= threshold:
                score = _score_headline(h['title'])
                matched.append({'title': h['title'], 'score': score})

        if matched:
            avg_score = sum(m['score'] for m in matched) / len(matched)
        else:
            avg_score = 0.0

        sentiment_data[mid] = {
            'score': round(avg_score, 4),
            'matched_headlines': matched[:5],  # top 5 for report
            'headline_count': len(matched),
        }

    return sentiment_data
