"""
ArXiv paper research module — searches for prediction market &
forecasting papers, tracks seen papers, extracts insights.

Runs daily as part of the pipeline:
  - Queries ArXiv API for new papers in relevant categories
  - Deduplicates against previously seen papers
  - Extracts actionable insights from abstracts
  - Optionally uses Copilot API to summarize key findings
  - Logs findings to data/history/arxiv_papers.json
"""
import json
import os
import sys
import re
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_client

_BASE = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
_PAPERS_DB = os.path.join(_BASE, 'data', 'history', 'arxiv_papers.json')
_INSIGHTS_LOG = os.path.join(_BASE, 'data', 'history', 'arxiv_insights.jsonl')

# ArXiv Atom XML namespace
ATOM_NS = '{http://www.w3.org/2005/Atom}'

# Default search queries targeting prediction market research
DEFAULT_QUERIES = [
    'prediction market forecasting accuracy',
    'Kelly criterion betting optimal sizing',
    'calibration probabilistic forecasting',
    'information aggregation prediction markets',
    'automated market maker scoring rules',
]

# ArXiv categories most relevant to prediction markets
RELEVANT_CATEGORIES = [
    'q-fin.TR',   # Trading and Market Microstructure
    'q-fin.PM',   # Portfolio Management
    'q-fin.RM',   # Risk Management
    'stat.ML',    # Machine Learning
    'cs.AI',      # Artificial Intelligence
    'cs.GT',      # Computer Science and Game Theory
    'econ.GN',    # General Economics
    'stat.AP',    # Statistics Applications
]


# ---------------------------------------------------------------------------
# Paper database
# ---------------------------------------------------------------------------

def _load_papers_db():
    """Load the database of seen papers."""
    if not os.path.exists(_PAPERS_DB):
        return {'papers': {}, 'last_check': None}
    with open(_PAPERS_DB, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_papers_db(db):
    """Save the papers database."""
    os.makedirs(os.path.dirname(_PAPERS_DB), exist_ok=True)
    with open(_PAPERS_DB, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def _log_insight(entry):
    """Append an insight entry to the log."""
    os.makedirs(os.path.dirname(_INSIGHTS_LOG), exist_ok=True)
    with open(_INSIGHTS_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


# ---------------------------------------------------------------------------
# ArXiv API search
# ---------------------------------------------------------------------------

def _build_query(search_terms, categories=None, max_results=10):
    """
    Build an ArXiv API query URL.
    ArXiv API docs: https://info.arxiv.org/help/api/user-manual.html
    """
    # Build search query
    terms = search_terms.replace(' ', '+AND+')
    query = f'all:{terms}'

    # Add category filter if specified
    if categories:
        cat_filter = '+OR+'.join(f'cat:{c}' for c in categories)
        query = f'({query})+AND+({cat_filter})'

    params = {
        'search_query': query,
        'start': '0',
        'max_results': str(max_results),
        'sortBy': 'lastUpdatedDate',
        'sortOrder': 'descending',
    }

    return params


def _parse_arxiv_response(xml_text):
    """
    Parse ArXiv Atom XML response into a list of paper dicts.
    """
    papers = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"  ArXiv XML parse error: {e}")
        return papers

    for entry in root.findall(f'{ATOM_NS}entry'):
        paper_id_el = entry.find(f'{ATOM_NS}id')
        title_el = entry.find(f'{ATOM_NS}title')
        summary_el = entry.find(f'{ATOM_NS}summary')
        published_el = entry.find(f'{ATOM_NS}published')
        updated_el = entry.find(f'{ATOM_NS}updated')

        if paper_id_el is None or title_el is None:
            continue

        paper_id = paper_id_el.text.strip()
        # Extract arXiv ID from URL (e.g., http://arxiv.org/abs/2301.12345v1)
        arxiv_id = paper_id.split('/abs/')[-1] if '/abs/' in paper_id else paper_id

        title = ' '.join(title_el.text.strip().split())
        summary = ' '.join(summary_el.text.strip().split()) if summary_el is not None else ''

        # Authors
        authors = []
        for author_el in entry.findall(f'{ATOM_NS}author'):
            name_el = author_el.find(f'{ATOM_NS}name')
            if name_el is not None:
                authors.append(name_el.text.strip())

        # Categories
        categories = []
        for cat_el in entry.findall(f'{ATOM_NS}category'):
            term = cat_el.get('term', '')
            if term:
                categories.append(term)

        # Links
        pdf_link = ''
        for link_el in entry.findall(f'{ATOM_NS}link'):
            if link_el.get('title') == 'pdf':
                pdf_link = link_el.get('href', '')
                break

        papers.append({
            'arxiv_id': arxiv_id,
            'title': title,
            'summary': summary,
            'authors': authors[:5],  # Cap at 5 authors
            'categories': categories,
            'published': published_el.text.strip() if published_el is not None else '',
            'updated': updated_el.text.strip() if updated_el is not None else '',
            'url': paper_id,
            'pdf_url': pdf_link,
        })

    return papers


def search_papers(query_text, max_results=10):
    """
    Search ArXiv for papers matching the query.
    Returns list of paper dicts.
    """
    params = _build_query(query_text, max_results=max_results)

    # Build URL manually since ArXiv API uses specific query format
    base_url = 'http://export.arxiv.org/api/query'
    param_str = '&'.join(f'{k}={v}' for k, v in params.items())
    url = f'{base_url}?{param_str}'

    try:
        xml_text = http_client.get_text(url, timeout=30)
        if not xml_text:
            return []
        return _parse_arxiv_response(xml_text)
    except Exception as e:
        print(f"  ArXiv search failed for '{query_text}': {e}")
        return []


# ---------------------------------------------------------------------------
# Insight extraction
# ---------------------------------------------------------------------------

# Keywords that indicate actionable insights for prediction markets
_INSIGHT_KEYWORDS = [
    'kelly', 'optimal bet', 'position sizing', 'bankroll',
    'calibration', 'overconfidence', 'underconfidence',
    'brier score', 'log loss', 'probability score',
    'market efficiency', 'price discovery', 'information aggregation',
    'mean reversion', 'momentum', 'contrarian',
    'volatility', 'risk management', 'drawdown',
    'ensemble', 'model combination', 'meta-learning',
    'sentiment analysis', 'news impact', 'event study',
    'liquidity', 'bid-ask spread', 'slippage',
    'bayesian', 'prior', 'posterior', 'updating',
]


def _extract_insights_from_abstract(paper):
    """
    Extract actionable insights from a paper's abstract.
    Returns a list of insight strings.
    """
    summary = paper.get('summary', '').lower()
    title = paper.get('title', '').lower()
    text = title + ' ' + summary

    insights = []

    # Check for specific actionable patterns
    patterns = [
        (r'improv\w+ (accuracy|calibration|performance) by (\d+)', 'performance_improvement'),
        (r'optimal .{0,30}(fraction|size|allocation)', 'position_sizing'),
        (r'(outperform|beat|superior to) .{0,40}(baseline|benchmark|market)', 'strategy_edge'),
        (r'(overconfiden|underconfiden|miscalibrat)', 'calibration_finding'),
        (r'(sentiment|news|social media) .{0,30}(predict|correlat|impact)', 'sentiment_signal'),
        (r'(mean reversion|momentum|contrarian)', 'market_pattern'),
        (r'(ensemble|combin|aggregat) .{0,30}(forecast|predict|model)', 'model_combination'),
        (r'(kelly|bankroll|bet siz)', 'betting_strategy'),
        (r'(liquidity|spread|slippage)', 'execution_insight'),
    ]

    for pattern, insight_type in patterns:
        match = re.search(pattern, text)
        if match:
            # Extract surrounding context (±50 chars)
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end].strip()
            insights.append({
                'type': insight_type,
                'context': context,
                'matched': match.group(0),
            })

    return insights


def _relevance_score(paper):
    """
    Score a paper's relevance to our prediction market system (0-1).
    Higher = more relevant.
    """
    summary = paper.get('summary', '').lower()
    title = paper.get('title', '').lower()
    text = title + ' ' + summary

    score = 0.0
    total_keywords = len(_INSIGHT_KEYWORDS)

    for kw in _INSIGHT_KEYWORDS:
        if kw in text:
            score += 1.0

    # Normalize
    score = min(1.0, score / max(1, total_keywords * 0.15))

    # Bonus for prediction market specific terms
    pm_terms = ['prediction market', 'polymarket', 'betting market',
                'forecasting tournament', 'metaculus', 'manifold']
    for term in pm_terms:
        if term in text:
            score = min(1.0, score + 0.2)

    return round(score, 3)


# ---------------------------------------------------------------------------
# Copilot API summarization (optional, uses 1 API call)
# ---------------------------------------------------------------------------

def _summarize_with_copilot(new_papers):
    """
    Use GitHub Models API to summarize key findings from new papers.
    Consumes 1 API call from the daily budget.
    Returns a summary string or None.
    """
    token = os.environ.get('GITHUB_TOKEN', '')
    if not token or not new_papers:
        return None

    # Build a condensed paper list for the prompt
    paper_summaries = []
    for p in new_papers[:5]:  # Max 5 papers to keep prompt short
        paper_summaries.append(
            f"- {p['title']} ({p['arxiv_id']}): {p['summary'][:200]}..."
        )

    prompt = (
        "Below are recent arXiv papers relevant to a Polymarket prediction system "
        "that uses statistical analysis, sentiment analysis, arbitrage detection, "
        "and Kelly criterion for bet sizing.\n\n"
        + '\n'.join(paper_summaries) +
        "\n\nFor each paper, extract ONE specific actionable insight that could "
        "improve our prediction system. Focus on: parameter tuning, new signals, "
        "risk management, or calibration improvements. "
        "Return JSON array: [{\"paper\": \"arxiv_id\", \"insight\": \"...\", "
        "\"action\": \"specific parameter or strategy change\"}]"
    )

    try:
        payload = {
            'messages': [
                {'role': 'system', 'content': 'You are a quantitative researcher. Be concise and actionable.'},
                {'role': 'user', 'content': prompt},
            ],
            'model': 'gpt-4o',
            'max_tokens': 500,
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
        if resp and 'choices' in resp:
            return resp['choices'][0].get('message', {}).get('content', '')
    except Exception as e:
        print(f"  Copilot summarization failed: {e}")

    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def check_arxiv(config):
    """
    Main entry point: search ArXiv for new papers, extract insights.

    Returns dict with:
        new_papers: list of new paper dicts
        total_in_db: int
        insights: list of extracted insights
        copilot_summary: str or None
        queries_searched: int
    """
    arxiv_cfg = config.get('arxiv', {})
    queries = arxiv_cfg.get('search_queries', DEFAULT_QUERIES)
    max_results = arxiv_cfg.get('max_results_per_query', 5)
    use_copilot = arxiv_cfg.get('use_copilot', False)
    min_relevance = arxiv_cfg.get('min_relevance_score', 0.1)

    db = _load_papers_db()
    seen_ids = set(db.get('papers', {}).keys())
    all_new = []
    queries_searched = 0

    print(f"  Searching {len(queries)} queries, {len(seen_ids)} papers in DB")

    for query in queries:
        papers = search_papers(query, max_results=max_results)
        queries_searched += 1

        for paper in papers:
            aid = paper['arxiv_id']
            if aid in seen_ids:
                continue

            # Score relevance
            relevance = _relevance_score(paper)
            paper['relevance_score'] = relevance

            if relevance < min_relevance:
                continue

            # Extract insights
            insights = _extract_insights_from_abstract(paper)
            paper['insights'] = insights

            # Add to database (including abstract for concept extraction)
            db['papers'][aid] = {
                'title': paper['title'],
                'abstract': paper.get('summary', '')[:1500],  # cap at 1500 chars
                'authors': paper['authors'],
                'categories': paper['categories'],
                'published': paper['published'],
                'relevance_score': relevance,
                'insights_count': len(insights),
                'first_seen': datetime.now(timezone.utc).isoformat(),
                'url': paper['url'],
            }
            seen_ids.add(aid)
            all_new.append(paper)

    # Sort by relevance
    all_new.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)

    # Copilot summarization (optional, costs 1 API call)
    copilot_summary = None
    if use_copilot and all_new:
        copilot_summary = _summarize_with_copilot(all_new)

    # Log insights
    all_insights = []
    for paper in all_new:
        for insight in paper.get('insights', []):
            entry = {
                'arxiv_id': paper['arxiv_id'],
                'title': paper['title'],
                'insight_type': insight['type'],
                'context': insight['context'],
                'relevance': paper['relevance_score'],
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            _log_insight(entry)
            all_insights.append(entry)

    # Update last check time and save
    db['last_check'] = datetime.now(timezone.utc).isoformat()
    _save_papers_db(db)

    if all_new:
        print(f"  Found {len(all_new)} new papers, {len(all_insights)} insights extracted")
        for p in all_new[:3]:
            print(f"    [{p['relevance_score']:.2f}] {p['title'][:70]}")
    else:
        print("  No new papers found")

    return {
        'new_papers': all_new,
        'total_in_db': len(db['papers']),
        'insights': all_insights,
        'copilot_summary': copilot_summary,
        'queries_searched': queries_searched,
    }
