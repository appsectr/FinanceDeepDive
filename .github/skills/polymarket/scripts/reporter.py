"""
HTML report generator — dark-theme report with 5 sections.
Outputs to data/reports/YYYY-MM-DD.html and returns html string.
"""
import os
from datetime import datetime, timezone


def _esc(text):
    """Escape HTML entities."""
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def generate_report(predictions, accuracy_metrics, improvements, arb_scores, sentiment_data, config):
    """
    Generate full HTML report.
    Returns (html_string, file_path).
    """
    now = datetime.now(timezone.utc)
    now_str = now.strftime('%Y-%m-%d %H:%M UTC')
    date_str = now.strftime('%Y-%m-%d')

    # Build sections
    opps_html = _section_opportunities(predictions)
    perf_html = _section_performance(accuracy_metrics)
    improve_html = _section_improvements(improvements)
    arb_html = _section_arbitrage(predictions, arb_scores)
    sent_html = _section_sentiment(predictions, sentiment_data)

    html = f'''<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Polymarket Analiz — {date_str}</title>
<style>
  :root {{ --bg: #0f172a; --card: #1e293b; --border: #334155; --text: #e2e8f0; --muted: #94a3b8; --accent: #818cf8; --green: #34d399; --red: #f87171; --yellow: #fbbf24; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); padding: 2rem; line-height: 1.6; }}
  .container {{ max-width: 1400px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; font-weight: 700; margin-bottom: 0.25rem; }}
  h2 {{ font-size: 1.2rem; font-weight: 600; margin: 2rem 0 0.75rem; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.4rem; }}
  .subtitle {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 1.5rem; }}
  .stats {{ display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }}
  .stat {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem 1.25rem; min-width: 140px; }}
  .stat-label {{ font-size: 0.7rem; text-transform: uppercase; color: var(--muted); letter-spacing: 0.05em; }}
  .stat-value {{ font-size: 1.3rem; font-weight: 700; color: var(--accent); }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card); border-radius: 8px; overflow: hidden; border: 1px solid var(--border); margin-bottom: 1rem; }}
  thead {{ background: #0f172a; }}
  th {{ text-align: left; padding: 0.75rem 1rem; font-size: 0.72rem; text-transform: uppercase; color: var(--muted); letter-spacing: 0.05em; white-space: nowrap; }}
  td {{ padding: 0.6rem 1rem; border-top: 1px solid var(--border); font-size: 0.85rem; vertical-align: middle; }}
  tr:hover {{ background: rgba(129,140,248,0.06); }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; color: #fff; }}
  .badge-yes {{ background: #166534; }}
  .badge-no {{ background: #991b1b; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .prob-bar {{ height: 5px; background: var(--border); border-radius: 3px; overflow: hidden; width: 80px; display: inline-block; vertical-align: middle; margin-left: 6px; }}
  .prob-fill {{ height: 100%; border-radius: 3px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 0.75rem; }}
  .pill {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 0.7rem; background: var(--border); margin: 1px; }}
  .footer {{ margin-top: 2rem; font-size: 0.75rem; color: var(--muted); text-align: center; }}
  .score-bar {{ display: flex; gap: 2px; height: 14px; border-radius: 3px; overflow: hidden; width: 120px; }}
  .score-seg {{ height: 100%; }}
</style>
</head>
<body>
<div class="container">
  <h1>Polymarket Gunluk Analiz</h1>
  <p class="subtitle">{now_str} &mdash; Otomatik olarak olusturuldu</p>

  <div class="stats">
    <div class="stat"><div class="stat-label">Bulunan Firsat</div><div class="stat-value">{len(predictions)}</div></div>
    <div class="stat"><div class="stat-label">Tahmin Isabeti</div><div class="stat-value">{_pct(accuracy_metrics.get('hit_rate', 0))}</div></div>
    <div class="stat"><div class="stat-label">Brier Skor</div><div class="stat-value">{accuracy_metrics.get('avg_brier_score', '-')}</div></div>
    <div class="stat"><div class="stat-label">Iyilestirme</div><div class="stat-value">{improvements.get('total_adjustments', 0)}</div></div>
  </div>

  {opps_html}
  {perf_html}
  {improve_html}
  {arb_html}
  {sent_html}

  <p class="footer">Kaynak: Polymarket Gamma API &mdash; Gurultu filtresi aktif &mdash; Self-improving system v1</p>
</div>
</body>
</html>'''

    # Save
    base = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
    report_dir = os.path.join(base, 'data', 'reports')
    os.makedirs(report_dir, exist_ok=True)
    out_path = os.path.join(report_dir, f'{date_str}.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Report saved: {out_path}")
    return html, out_path


def _pct(val):
    if isinstance(val, (int, float)):
        return f'{val * 100:.1f}%'
    return '-'


def _score_color(score):
    if score >= 0.7:
        return 'var(--green)'
    if score >= 0.4:
        return 'var(--yellow)'
    return 'var(--red)'


def _section_opportunities(predictions):
    if not predictions:
        return '<h2>Firsatlar</h2><p style="color:var(--muted)">Bugun kriter lere uyan firsat bulunamadi.</p>'

    rows = ''
    for i, p in enumerate(predictions[:30], 1):
        side = p['predicted_side']
        badge_cls = 'badge-yes' if side.upper() == 'YES' else 'badge-no'
        prob = p.get('predicted_prob', 0)
        comp = p.get('composite_score', 0)
        bar_w = int(comp * 100)
        bar_color = _score_color(comp)
        scores = p.get('scores', {})

        # Mini score breakdown bar
        s_stat = scores.get('statistical', 0)
        s_sent = scores.get('sentiment', 0)
        s_arb = scores.get('arbitrage', 0)
        s_vol = scores.get('volume', 0)
        total_s = s_stat + s_sent + s_arb + s_vol
        if total_s > 0:
            w1 = int(s_stat / total_s * 100)
            w2 = int(s_sent / total_s * 100)
            w3 = int(s_arb / total_s * 100)
            w4 = 100 - w1 - w2 - w3
        else:
            w1 = w2 = w3 = w4 = 25

        rows += f'''
      <tr>
        <td>{i}</td>
        <td><a href="{_esc(p.get('url', '#'))}" target="_blank">{_esc(p['question'][:80])}</a></td>
        <td><span class="badge {badge_cls}">{_esc(side)}</span></td>
        <td class="num">{prob*100:.0f}%</td>
        <td class="num">
          {comp:.3f}
          <div class="prob-bar"><div class="prob-fill" style="width:{bar_w}%;background:{bar_color}"></div></div>
        </td>
        <td>
          <div class="score-bar" title="stat:{s_stat:.2f} sent:{s_sent:.2f} arb:{s_arb:.2f} vol:{s_vol:.2f}">
            <div class="score-seg" style="width:{w1}%;background:#818cf8"></div>
            <div class="score-seg" style="width:{w2}%;background:#f472b6"></div>
            <div class="score-seg" style="width:{w3}%;background:#34d399"></div>
            <div class="score-seg" style="width:{w4}%;background:#fbbf24"></div>
          </div>
        </td>
        <td class="num">${p.get('volume', 0):,.0f}</td>
        <td class="num">{p.get('kelly', 0)*100:.1f}%</td>
        <td>{_esc(p.get('ends_in', ''))}</td>
      </tr>'''

    return f'''<h2>Firsatlar ({len(predictions)})</h2>
  <table>
    <thead>
      <tr><th>#</th><th>Soru</th><th>Taraf</th><th>Oran</th><th>Skor</th><th>Dagilim</th><th>Hacim</th><th>Kelly</th><th>Bitis</th></tr>
    </thead>
    <tbody>{rows}
    </tbody>
  </table>
  <p style="font-size:0.7rem;color:var(--muted)">Dagilim: <span style="color:#818cf8">istatistik</span> <span style="color:#f472b6">duygu</span> <span style="color:#34d399">arbitraj</span> <span style="color:#fbbf24">hacim</span></p>'''


def _section_performance(metrics):
    total = metrics.get('total_predictions', 0)
    if total == 0:
        return '<h2>Tahmin Performansi</h2><p style="color:var(--muted)">Henuz yeterli tahmin verisi yok.</p>'

    hit = metrics.get('hit_rate', 0)
    brier = metrics.get('avg_brier_score', 0)
    correct = metrics.get('correct', 0)

    # Calibration table
    cal = metrics.get('calibration', {})
    cal_rows = ''
    for bucket_str in sorted(cal.keys()):
        data = cal[bucket_str]
        exp = data['expected']
        act = data['actual']
        cnt = data['count']
        diff = act - exp
        color = 'var(--green)' if abs(diff) < 0.1 else 'var(--yellow)' if abs(diff) < 0.2 else 'var(--red)'
        cal_rows += f'<tr><td class="num">{exp*100:.0f}%</td><td class="num" style="color:{color}">{act*100:.1f}%</td><td class="num">{diff*100:+.1f}%</td><td class="num">{cnt}</td></tr>'

    # Recent results
    recent = metrics.get('recent_results', [])
    recent_rows = ''
    for r in recent[-10:]:
        icon = '&#10003;' if r.get('correct') else '&#10007;'
        color = 'var(--green)' if r.get('correct') else 'var(--red)'
        recent_rows += f'''<tr>
          <td>{_esc(r.get('date', ''))}</td>
          <td>{_esc(r.get('question', '')[:60])}</td>
          <td>{_esc(r.get('predicted', ''))}</td>
          <td>{_esc(r.get('actual', ''))}</td>
          <td style="color:{color};font-weight:700">{icon}</td>
          <td class="num">{r.get('brier', 0):.3f}</td>
        </tr>'''

    return f'''<h2>Tahmin Performansi</h2>
  <div class="stats">
    <div class="stat"><div class="stat-label">Toplam</div><div class="stat-value">{total}</div></div>
    <div class="stat"><div class="stat-label">Dogru</div><div class="stat-value">{correct}</div></div>
    <div class="stat"><div class="stat-label">Isabet</div><div class="stat-value">{hit*100:.1f}%</div></div>
    <div class="stat"><div class="stat-label">Brier</div><div class="stat-value">{brier:.4f}</div></div>
  </div>
  <div style="display:flex;gap:1.5rem;flex-wrap:wrap">
    <div style="flex:1;min-width:280px">
      <h3 style="font-size:0.85rem;color:var(--muted);margin-bottom:0.5rem">Kalibrasyon</h3>
      <table><thead><tr><th>Beklenen</th><th>Gerceklesen</th><th>Fark</th><th>Sayi</th></tr></thead><tbody>{cal_rows}</tbody></table>
    </div>
    <div style="flex:2;min-width:400px">
      <h3 style="font-size:0.85rem;color:var(--muted);margin-bottom:0.5rem">Son Tahminler</h3>
      <table><thead><tr><th>Tarih</th><th>Soru</th><th>Tahmin</th><th>Sonuc</th><th></th><th>Brier</th></tr></thead><tbody>{recent_rows}</tbody></table>
    </div>
  </div>'''


def _section_improvements(improvements):
    changes = improvements.get('config_changes', [])
    suggestions = improvements.get('copilot_suggestions', [])

    if not changes and not suggestions:
        return '<h2>Kendini Iyilestirme</h2><p style="color:var(--muted)">Bu calismada parametre degisikligi yapilmadi.</p>'

    items = ''
    for c in changes:
        items += f'''<div class="card">
      <div style="font-weight:600;font-size:0.9rem">{_esc(c.get('type', ''))}</div>
      <div style="font-size:0.85rem">{_esc(c.get('detail', ''))}</div>
      <div style="font-size:0.75rem;color:var(--muted)">Neden: {_esc(c.get('reason', ''))}</div>
    </div>'''

    for s in suggestions:
        items += f'''<div class="card">
      <div style="font-weight:600;font-size:0.9rem">Copilot Onerisi</div>
      <div style="font-size:0.82rem;white-space:pre-wrap">{_esc(s[:500])}</div>
    </div>'''

    return f'<h2>Kendini Iyilestirme ({len(changes)} degisiklik)</h2>{items}'


def _section_arbitrage(predictions, arb_scores):
    anomalies = [(p, arb_scores.get(p['market_id'], {})) for p in predictions if arb_scores.get(p['market_id'], {}).get('has_anomaly')]

    if not anomalies:
        return '<h2>Arbitraj / Spread Anomali</h2><p style="color:var(--muted)">Anormal spread tespit edilmedi.</p>'

    rows = ''
    for p, arb in anomalies[:15]:
        rows += f'''<tr>
      <td><a href="{_esc(p.get('url', '#'))}" target="_blank">{_esc(p['question'][:70])}</a></td>
      <td class="num">{arb.get('spread_pct', 0)*100:.1f}%</td>
      <td class="num">{arb.get('arb_score', 0):.3f}</td>
      <td class="num">{arb.get('kelly_fraction', 0)*100:.1f}%</td>
    </tr>'''

    return f'''<h2>Arbitraj / Spread Anomali ({len(anomalies)})</h2>
  <table>
    <thead><tr><th>Market</th><th>Spread</th><th>Arb Skor</th><th>Kelly</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>'''


def _section_sentiment(predictions, sentiment_data):
    items_with_sent = [(p, sentiment_data.get(p['market_id'], {})) for p in predictions if sentiment_data.get(p['market_id'], {}).get('matched_headlines')]

    if not items_with_sent:
        return '<h2>Duygu Analizi (Sentiment)</h2><p style="color:var(--muted)">Eslesen haber haberleri bulunamadi.</p>'

    cards = ''
    for p, sent in items_with_sent[:10]:
        score = sent.get('score', 0)
        color = 'var(--green)' if score > 0.1 else 'var(--red)' if score < -0.1 else 'var(--muted)'
        headlines = sent.get('matched_headlines', [])[:5]
        hl_html = ''.join(f'<div class="pill">{_esc((h["title"] if isinstance(h, dict) else str(h))[:80])}</div>' for h in headlines)
        cards += f'''<div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div style="font-weight:600;font-size:0.88rem">{_esc(p['question'][:70])}</div>
        <div style="font-size:1rem;font-weight:700;color:{color}">{score:+.2f}</div>
      </div>
      <div style="margin-top:0.3rem">{hl_html}</div>
    </div>'''

    return f'<h2>Duygu Analizi ({len(items_with_sent)} market)</h2>{cards}'
