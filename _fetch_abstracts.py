#!/usr/bin/env python3
"""Fetch abstracts from ArXiv for relevant papers and print them."""
import json, sys, time
sys.path.insert(0, '.github/skills/polymarket/scripts')
import http_client
from xml.etree import ElementTree as ET

ATOM_NS = '{http://www.w3.org/2005/Atom}'

data = json.load(open('data/history/arxiv_papers.json'))
papers = data['papers']

relevant = [(aid, p) for aid, p in papers.items() if p.get('relevance_score', 0) >= 0.4]
relevant.sort(key=lambda x: x[1]['relevance_score'], reverse=True)

print(f'Fetching abstracts for {len(relevant)} relevant papers...\n')

for aid, p in relevant:
    url = f'http://export.arxiv.org/api/query?id_list={aid}&max_results=1'
    try:
        xml_text = http_client.get_text(url, timeout=15)
        root = ET.fromstring(xml_text)
        entry = root.find(f'{ATOM_NS}entry')
        if entry is not None:
            summary_el = entry.find(f'{ATOM_NS}summary')
            summary = ' '.join(summary_el.text.strip().split()) if summary_el is not None else 'N/A'
            print(f'=== [{p["relevance_score"]:.2f}] {p["title"]} ===')
            print(summary)
            print()
        time.sleep(0.5)  # Be nice to ArXiv API
    except Exception as e:
        print(f'FAIL {aid}: {e}')
