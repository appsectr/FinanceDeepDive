"""
Rule-based sentiment analysis via RSS news feeds.
Uses urllib + xml.etree.ElementTree — no 3rd party deps.
Matches news headlines to market questions with stem-based
lexicon and phrase matching.  Scores -1.0 to +1.0.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_client

# ---------------------------------------------------------------------------
# Stem-based lexicon: each stem matches any word starting with it.
# e.g. 'approv' matches approve, approved, approval, approving
# ---------------------------------------------------------------------------
POSITIVE_STEMS = [
    'approv', 'pass', 'sign', 'enact', 'ratif',
    'win', 'wins', 'winning', 'winner', 'won', 'victor', 'succe', 'triumph',
    'gain', 'gains', 'boost', 'surg', 'soar', 'rise', 'risen', 'rising', 'increas', 'jump',
    'rally', 'rallied', 'recover', 'rebound', 'upturn', 'uptick',
    'support', 'endors', 'back', 'champion',
    'agree', 'deal', 'pact', 'treaty', 'accord', 'alliance',
    'progress', 'advanc', 'improv', 'reform', 'innovat',
    'breakthro', 'mileston', 'achiev', 'accompl',
    'lead', 'dominat', 'outperform', 'beat', 'exceed',
    'confirm', 'uphold', 'upheld', 'validat',
    'bipartisan', 'unanim', 'landmark', 'histor',
    'optimis', 'confiden', 'strong', 'strengthen', 'resili',
    'bullish', 'outpac', 'profitabl', 'profit', 'revenue',
    'earn', 'dividend', 'growth', 'grow', 'expand',
    'record high', 'all time high', 'new high', 'highest',
    'upgrad', 'promot', 'elevat', 'rais', 'hik',
    'peacef', 'ceasefire', 'truce', 'de-escalat', 'deescalat',
    'stabiliz', 'calm', 'resolv', 'resolut', 'settl',
    'launch', 'unveil', 'introduc', 'inaugurat',
    'accept', 'embrac', 'adopt', 'implement',
    'prosper', 'thrive', 'flourish', 'boom',
    'safe', 'secur', 'protect', 'guarante',
    'popular', 'favorab', 'favour', 'favor',
]

NEGATIVE_STEMS = [
    'reject', 'deni', 'deny', 'block', 'fail', 'collaps',
    'lose', 'lost', 'defeat', 'veto', 'oppos',
    'crisis', 'crash', 'plummet', 'plunge', 'tumbl', 'tank',
    'declin', 'drop', 'fall', 'fell', 'falling', 'slide', 'slump', 'sink', 'sunk',
    'risk', 'threat', 'warn', 'fear', 'panic', 'alarm',
    'concern', 'worr', 'anxiet', 'anxious',
    'scandal', 'investigat', 'probe', 'indict', 'charg', 'accus', 'alleg',
    'impeach', 'resign', 'oust', 'remov', 'fire', 'fired', 'sack',
    'suspend', 'sanction', 'embargo', 'penalt', 'fine', 'fined',
    'tariff', 'shutdown', 'deadlock', 'stall', 'gridlock', 'impasse',
    'withdraw', 'retreat', 'pullback', 'pull back',
    'delay', 'postpon', 'defer',
    'uncertain', 'volatil', 'unstable', 'turmoil', 'chaos',
    'controversi', 'disput', 'conflict', 'tension', 'escalat',
    'bearish', 'downturn', 'recession', 'slowdown', 'contract',
    'bankrupt', 'default', 'insolvenc', 'liquidat',
    'cut', 'cuts', 'slash', 'reduc', 'layoff', 'downgrad', 'demot',
    'attack', 'strike', 'bomb', 'shell', 'assault', 'invad', 'invasion',
    'war', 'combat', 'hostil', 'aggress',
    'kill', 'death', 'dead', 'casualt', 'wound',
    'destroy', 'destruct', 'devastat', 'damag',
    'ban', 'bans', 'banned', 'banning', 'prohibit', 'restrict', 'limit', 'curb', 'clamp',
    'fraud', 'corrupt', 'embezzl', 'launder',
    'miss', 'missed', 'shortfall', 'underperform',
    'protest', 'unrest', 'riot', 'revolt', 'rebel',
    'inflat', 'stagflat', 'deflat',
    'weak', 'weaken', 'vulnerabl', 'expos',
    'violat', 'breach', 'infring',
    'sue', 'sued', 'sues', 'suing', 'lawsuit', 'litigat',
    'record low', 'all time low', 'new low', 'lowest',
    'toxic', 'hazard', 'catastroph', 'disast',
]

# Compile stems into exact-word or prefix matchers
def _build_stem_set(stems):
    """Return (exact_set, prefix_list) for fast matching."""
    exact = set()
    prefixes = []
    for s in stems:
        if ' ' in s:
            continue  # phrases handled separately
        if len(s) <= 3:
            exact.add(s)
        else:
            prefixes.append(s)
    return exact, prefixes

_POS_EXACT, _POS_PREFIX = _build_stem_set(POSITIVE_STEMS)
_NEG_EXACT, _NEG_PREFIX = _build_stem_set(NEGATIVE_STEMS)

# Phrase patterns (multi-word): (regex_pattern, polarity_score)
PHRASE_PATTERNS = []
for stem in POSITIVE_STEMS:
    if ' ' in stem:
        PHRASE_PATTERNS.append((re.compile(re.escape(stem), re.I), +1.0))
for stem in NEGATIVE_STEMS:
    if ' ' in stem:
        PHRASE_PATTERNS.append((re.compile(re.escape(stem), re.I), -1.0))

# Extra phrase patterns
PHRASE_PATTERNS.extend([
    (re.compile(r'\bstep(?:s|ped|ping)? down\b', re.I), -0.8),
    (re.compile(r'\bgive(?:s|n)? up\b', re.I), -0.6),
    (re.compile(r'\bblow(?:s|n|ing)? up\b', re.I), -0.7),
    (re.compile(r'\bshut(?:s|ting)? down\b', re.I), -0.7),
    (re.compile(r'\bbail(?:s|ed|ing)? out\b', re.I), -0.5),
    (re.compile(r'\bbeat(?:s|ing)? expect\w*\b', re.I), +0.9),
    (re.compile(r'\bmiss(?:es|ed|ing)? expect\w*\b', re.I), -0.9),
    (re.compile(r'\bbetter than expect\w*\b', re.I), +0.8),
    (re.compile(r'\bworse than expect\w*\b', re.I), -0.8),
    (re.compile(r'\bgreen light\b', re.I), +0.7),
    (re.compile(r'\bred flag\b', re.I), -0.6),
])

AMPLIFIERS = {
    'very', 'extremely', 'strongly', 'significantly', 'sharply',
    'dramatically', 'massively', 'hugely', 'overwhelmingly',
    'substantially', 'considerably', 'remarkably', 'strikingly',
}
NEGATORS = {
    'not', 'no', 'never', 'neither', 'nor', "don't", "doesn't",
    "didn't", "won't", "can't", "cannot", "hardly", "barely",
    "scarcely", "unlikely", "unable",
}


# ---------------------------------------------------------------------------
# Default RSS feeds — broad coverage across domains
# ---------------------------------------------------------------------------
DEFAULT_FEEDS = [
    # General news
    'https://news.google.com/rss/search?q=politics&hl=en-US&gl=US&ceid=US:en',
    'https://news.google.com/rss/search?q=geopolitics+policy&hl=en-US&gl=US&ceid=US:en',
    'https://news.google.com/rss/search?q=economy+regulation&hl=en-US&gl=US&ceid=US:en',
    # Financial / markets
    'https://news.google.com/rss/search?q=stock+market+earnings&hl=en-US&gl=US&ceid=US:en',
    'https://news.google.com/rss/search?q=crypto+bitcoin+ethereum&hl=en-US&gl=US&ceid=US:en',
    'https://news.google.com/rss/search?q=oil+commodities+prices&hl=en-US&gl=US&ceid=US:en',
    # Geopolitics / conflicts
    'https://news.google.com/rss/search?q=war+military+conflict&hl=en-US&gl=US&ceid=US:en',
    'https://news.google.com/rss/search?q=sanctions+tariff+trade&hl=en-US&gl=US&ceid=US:en',
    # Sports / culture (Polymarket has these too)
    'https://news.google.com/rss/search?q=sports+championship+playoffs&hl=en-US&gl=US&ceid=US:en',
    # Tech / AI
    'https://news.google.com/rss/search?q=AI+technology+regulation&hl=en-US&gl=US&ceid=US:en',
]


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
        for entry in root.iter('{http://www.w3.org/2005/Atom}entry'):
            title_el = entry.find('{http://www.w3.org/2005/Atom}title')
            if title_el is not None and title_el.text:
                items.append({'title': title_el.text.strip(), 'published': ''})

    return items


def fetch_news(config=None):
    """Fetch all configured RSS feeds, return flat list of headline dicts."""
    if config is None:
        config = {}
    feeds = config.get('sentiment', {}).get('rss_feeds', DEFAULT_FEEDS)

    all_headlines = []
    seen_titles = set()
    for url in feeds:
        try:
            xml = http_client.get_text(url, timeout=10)
            items = _parse_rss(xml)
            for item in items:
                key = item['title'].lower().strip()
                if key not in seen_titles:
                    seen_titles.add(key)
                    all_headlines.append(item)
        except Exception:
            continue

    return all_headlines


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------
_STOP = frozenset({
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'will',
    'would', 'could', 'should', 'may', 'might', 'can', 'do', 'does', 'did',
    'has', 'have', 'had', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
    'by', 'from', 'this', 'that', 'it', 'its', 'or', 'and', 'but', 'if',
    'than', 'then', 'so', 'as', 'up', 'out', 'about', 'into', 'over',
    'after', 'before', 'between', 'under', 'again', 'there', 'here', 'when',
    'where', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'not', 'only', 'own', 'same',
    'what', 'which', 'who', 'whom', 'march', 'april', 'june', 'july',
    'january', 'february', 'august', 'september', 'october', 'november',
    'december', 'yes', 'end', 'day', 'month', 'year', 'next',
})


def _extract_keywords(question):
    """Extract meaningful keywords from a market question for matching."""
    words = re.findall(r'[a-zA-Z]+', question.lower())
    return {w for w in words if w not in _STOP and len(w) > 2}


# ---------------------------------------------------------------------------
# Stem-based word classifier
# ---------------------------------------------------------------------------
def _classify_word(clean):
    """Return +1 for positive, -1 for negative, 0 for neutral."""
    if clean in _POS_EXACT:
        return +1
    if clean in _NEG_EXACT:
        return -1
    for prefix in _POS_PREFIX:
        if clean.startswith(prefix):
            return +1
    for prefix in _NEG_PREFIX:
        if clean.startswith(prefix):
            return -1
    return 0


# ---------------------------------------------------------------------------
# Headline scoring
# ---------------------------------------------------------------------------
def _score_headline(headline_text):
    """Score a single headline: -1.0 to +1.0 using stem matching + phrases."""
    text_lower = headline_text.lower()
    score = 0.0

    # 1) Phrase-level scoring first
    for pattern, value in PHRASE_PATTERNS:
        if pattern.search(text_lower):
            score += value

    # 2) Word-level scoring with negation & amplification
    words = text_lower.split()
    negate = False
    for i, word in enumerate(words):
        clean = re.sub(r'[^a-z]', '', word)
        if not clean:
            continue
        if clean in NEGATORS:
            negate = True
            continue
        if clean in AMPLIFIERS:
            continue

        polarity = _classify_word(clean)
        if polarity == 0:
            negate = False
            continue

        amp = 1.5 if (i > 0 and re.sub(r'[^a-z]', '', words[i-1]) in AMPLIFIERS) else 1.0
        if negate:
            polarity = -polarity
        score += polarity * amp
        negate = False

    # Clamp to [-1.0, +1.0] with tanh-like scaling
    # This prevents any single headline from dominating
    if score == 0.0:
        return 0.0
    # Scale: ±1 word ≈ ±0.4, ±2 words ≈ ±0.7, ±3+ words ≈ ±0.85+
    import math
    return math.tanh(score * 0.5)


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
def analyze_sentiment(scan_results, config=None):
    """
    For each scanned market, find related news headlines and compute sentiment.
    Returns dict: market_id → {score, matched_headlines, headline_count, news_volume_score}.

    The news_volume_score is a separate signal based on the finding from
    "Can News Predict Oil Price Volatility?" — raw news count is a robust
    predictor independent of sentiment direction.
    """
    headlines = fetch_news(config)
    print(f"Fetched {len(headlines)} unique news headlines for sentiment analysis.")

    sentiment_data = {}

    # Track headline counts across all markets for normalization
    all_counts = []

    for r in scan_results:
        mid = r['id']
        keywords = _extract_keywords(r['question'])
        if not keywords:
            sentiment_data[mid] = {'score': 0.0, 'matched_headlines': [],
                                   'headline_count': 0, 'news_volume_score': 0.0}
            continue

        matched = []
        for h in headlines:
            htitle = h['title'].lower()
            # Match if at least 2 keywords appear in headline
            # (or 1 if keyword is long / likely a proper noun)
            matching_kws = {kw for kw in keywords if kw in htitle}
            if not matching_kws:
                continue
            threshold = 1 if any(len(kw) > 5 for kw in matching_kws) else 2
            if len(matching_kws) >= threshold:
                hscore = _score_headline(h['title'])
                matched.append({'title': h['title'], 'score': round(hscore, 4)})

        all_counts.append(len(matched))

        if matched:
            # Weighted average: more extreme scores count more
            total_weight = 0.0
            weighted_sum = 0.0
            for m in matched:
                w = 0.5 + abs(m['score'])  # non-neutral headlines count more
                weighted_sum += m['score'] * w
                total_weight += w
            avg_score = weighted_sum / total_weight if total_weight > 0 else 0.0
            # Confidence boost: more matching headlines → stronger signal
            import math
            confidence = math.tanh(len(matched) * 0.3)  # 1→0.29, 3→0.72, 5→0.91
            avg_score *= confidence
        else:
            avg_score = 0.0

        sentiment_data[mid] = {
            'score': round(avg_score, 4),
            'matched_headlines': sorted(matched, key=lambda x: abs(x['score']), reverse=True)[:5],
            'headline_count': len(matched),
            'news_volume_score': 0.0,  # filled in below
        }

    # Compute news_volume_score: normalized count across all markets
    # High news volume = market is "hot", prices likely more accurate
    # Low news volume = potential information asymmetry opportunity
    max_count = max(all_counts) if all_counts else 1
    for mid, data in sentiment_data.items():
        count = data['headline_count']
        if max_count > 0:
            import math
            # Logarithmic scaling: diminishing returns past ~10 articles
            data['news_volume_score'] = round(math.tanh(count / max(max_count * 0.3, 1)), 4)

    return sentiment_data
