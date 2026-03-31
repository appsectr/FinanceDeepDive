#!/usr/bin/env python3
import sys; sys.path.insert(0, '.github/skills/polymarket/scripts')
from sentiment import _score_headline, _classify_word

print("=== Word Classification ===")
for w in ['soaring', 'beats', 'beating', 'wins', 'winning', 'strikes', 'cuts', 'rises', 'drops', 'falls', 'gains']:
    c = _classify_word(w)
    print(f'  {w:15s} -> {c:+d}')

print("\n=== Headline Scoring ===")
headlines = [
    'Russia attacks Kyiv with massive drone strike',
    'Stock market rallies on strong earnings',
    'Nike beats quarterly earnings expectations',
    'Oil prices crash amid recession fears',
    'Biden signs landmark climate bill',
    'Iran sanctions tightened by EU',
    'Bitcoin surges past record high',
    'Trade war escalates as new tariffs imposed',
    'Ceasefire agreement reached in Gaza',
    'Markets soaring after positive jobs data',
    'Inflation fears rise sharply amid supply crisis',
]
for h in headlines:
    s = _score_headline(h)
    print(f'  {s:+.3f}  {h}')
