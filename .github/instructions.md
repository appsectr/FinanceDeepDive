# Polymarket Tahmin Sistemi — Ajan Talimatları

> Bu dosya, bu repo üzerinde çalışacak AI ajanları için temel kuralları ve bilgileri içerir.

---

## Repo Yapısı

```
FinanceDeepDive/
├── .github/
│   ├── instructions.md              ← Bu dosya
│   ├── workflows/
│   │   └── daily-report.yml         ← Günlük cron workflow (19:00 UTC)
│   └── skills/
│       └── polymarket/
│           └── scripts/
│               ├── main.py           ← Pipeline orchestrator
│               ├── http_client.py    ← urllib-based HTTP client
│               ├── scanner.py        ← Market tarama (Gamma API)
│               ├── analyzer.py       ← Zaman serisi analizi
│               ├── sentiment.py      ← RSS-based sentiment analizi
│               ├── arbitrage.py      ← Spread anomali tespiti
│               ├── predictor.py      ← Tahmin oluşturma & doğruluk izleme
│               ├── self_improve.py   ← Otomatik config ayarlama + Copilot API
│               ├── reporter.py       ← HTML rapor üretici (dark theme, JS sorting)
│               └── mailer.py         ← SendGrid e-posta gönderimi
├── data/
│   ├── config.json                   ← Tüm ayarlanabilir parametreler
│   ├── predictions/
│   │   ├── YYYY-MM-DD.json           ← Günlük tahminler
│   │   └── accuracy_log.json         ← Doğruluk metrikleri zaman serisi
│   ├── reports/
│   │   └── YYYY-MM-DD.html           ← Günlük HTML raporlar
│   └── history/
│       ├── price_history.json        ← Tarihsel fiyat verileri
│       └── improvements.jsonl        ← Self-improvement log
├── docs/
│   ├── research.md                   ← Araştırma notları ve strateji
│   └── brain.md                      ← Kavramsal eğitim dokümanı (Türkçe)
└── README.md
```

---

## Temel Kısıtlamalar

### 1. Sadece Python Standart Kütüphanesi
- **KESİNLİKLE pip paketi kullanma.** Tüm kod stdlib ile çalışmalı.
- İzin verilen modüller: `urllib.request`, `json`, `os`, `sys`, `re`, `xml.etree.ElementTree`, `datetime`, `math`, `pathlib`, `argparse`, `html`, `hashlib`, `collections`, `statistics`, vb.
- `requests`, `pandas`, `numpy`, `beautifulsoup4` gibi paketler **YASAK**.
- HTTP istekleri için `http_client.py` modülünü kullan.

### 2. Premium Request Bütçesi
- GitHub Models API (Copilot) için aylık **500 premium request** limiti var.
- Self-improvement modülü çağrı başına **maks 3** API isteği yapar.
- API çağrıları sadece `hit_rate < accuracy_target` olduğunda tetiklenir.
- Gereksiz API çağrısı yapma. Her çağrının net bir amacı olmalı.

### 3. Dil ve Stil
- Rapor ve log çıktıları **Türkçe** (ASCII-safe: ö→o, ü→u, ç→c, ş→s, ğ→g, ı→i).
- Dokümantasyon Türkçe yazılabilir (Unicode OK).
- HTML raporlar dark theme kullanır (CSS değişkenleri: `--bg:#0f172a`, `--card:#1e293b`, `--accent:#818cf8`).

---

## API Bilgileri

### Polymarket Gamma API
- **URL:** `https://gamma-api.polymarket.com/markets`
- **Metod:** GET
- **Parametreler:** `limit=500`, `offset=N`, `active=true`, `closed=false`
- **Header:** `User-Agent: Mozilla/5.0 (compatible; FinanceDeepDive/1.0)` — ZORUNLU (yoksa 403)
- **Rate limit:** Agresif polling yapma, batch 500 ile tarama yeterli

### Polymarket CLOB API
- **URL:** `https://clob.polymarket.com/midpoint?token_id=TOKEN_ID`
- **Amaç:** Order book midpoint fiyatı
- **Timeout:** 5 saniye (config'de ayarlanabilir)

### GitHub Models API (Copilot)
- **URL:** `https://models.inference.ai.azure.com/chat/completions`
- **Model:** `gpt-4o`
- **Auth:** `Authorization: Bearer $GITHUB_TOKEN`
- **Max tokens:** 300 (kısa, odaklı yanıtlar)
- **Kullanım:** Sadece self-improvement'ta, performans düşükse

### SendGrid API
- **URL:** `https://api.sendgrid.net/v3/mail/send`
- **Auth:** `Authorization: Bearer $SENDGRID_API_KEY`
- **Amaç:** Günlük rapor e-postası

---

## Config Yapısı (`data/config.json`)

| Bölüm | Anahtar Parametreler | Açıklama |
|--------|---------------------|----------|
| `scanner` | `min_volume`, `min_prob`, `max_prob`, `max_days_left` | Market filtreleri |
| `analyzer` | `sma_windows`, `volatility_window` | Zaman serisi pencereleri |
| `sentiment` | `rss_feeds`, `weight` | RSS kaynakları ve ağırlık |
| `scoring.weights` | `statistical`, `sentiment`, `arbitrage`, `volume` | Composite score ağırlıkları |
| `self_improve` | `accuracy_target`, `learning_rate`, `min_predictions_for_adjust` | Oto-ayar parametreleri |
| `email` | `to`, `from_email`, `subject_prefix` | E-posta ayarları |
| `exclude_patterns` | (regex listesi) | Gürültü filtreleri |
| `exclude_slug_prefixes` | (string listesi) | Slug-based filtreler |

Config dosyası self-improvement tarafından otomatik güncellenebilir. Manuel değişiklik yapmadan önce mevcut değerleri kaydet.

---

## Test Komutları

```bash
# Tam pipeline (e-posta göndermeden)
python3 .github/skills/polymarket/scripts/main.py --dry-run

# Sadece scanner test
python3 -c "
import sys; sys.path.insert(0, '.github/skills/polymarket/scripts')
import json, scanner
cfg = json.load(open('data/config.json'))
results = scanner.scan_markets(cfg)
print(f'{len(results)} opportunities found')
"

# Rapor doğrulama
open data/reports/$(date +%Y-%m-%d).html
```

---

## Workflow (GitHub Actions)

- **Dosya:** `.github/workflows/daily-report.yml`
- **Schedule:** `cron: '0 19 * * *'` (19:00 UTC = 22:00 Türkiye)
- **Manuel tetik:** `workflow_dispatch` destekli
- **Adımlar:**
  1. Checkout repo
  2. Setup Python 3.12
  3. Dizinleri oluştur (`data/predictions`, `data/reports`, `data/history`)
  4. Pipeline çalıştır (`--no-email` flag ile, e-posta sadece secret varsa)
  5. Raporu artifact olarak yükle (90 gün saklama)
  6. `data/` değişikliklerini auto-commit

- **Gerekli Secrets:**
  - `GITHUB_TOKEN` — otomatik sağlanır (self-improvement API çağrıları için)
  - `SENDGRID_API_KEY` — opsiyonel (e-posta göndermek için)

---

## Kodlama Kuralları

1. **Yeni modül eklerken:** `scripts/` dizinine koy, `main.py`'ye import et
2. **HTTP istekleri:** Her zaman `http_client.py` üzerinden yap
3. **Dosya yolları:** `os.path.normpath(os.path.join(os.path.dirname(__file__), ...))` pattern'ini kullan
4. **Hata yönetimi:** API çağrılarında try/except kullan, pipeline'ı kırma
5. **Veri formatı:** JSON kullan, tarihler ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ`)
6. **f-string'lerde HTML:** CSS/JS brace'leri `{{` ve `}}` olarak escape et
7. **Test:** Her değişiklikten sonra `--dry-run` ile pipeline'ı çalıştır
