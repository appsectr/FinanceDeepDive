# Polymarket Tahmin Sistemi — Kavramlar ve Mimari

> Bu doküman, sistemde kullanılan tüm kavramları Türkçe olarak açıklar. Mermaid diyagramlarla desteklenmiştir.

---

## 1. Prediction Market (Tahmin Piyasası) Nedir?

Prediction market, gelecekte olacak olayların olasılığını belirlemek için kullanılan bir piyasa mekanizmasıdır. Katılımcılar bir olayın gerçekleşip gerçekleşmeyeceğine "YES" veya "NO" kontratları satın alarak bahis yapar.

**Temel prensipler:**
- Bir kontratın fiyatı 0-1 (veya 0%-100%) arasındadır
- Fiyat, piyasanın o olayın gerçekleşme olasılığına dair konsensüsünü yansıtır
- Olay gerçekleşirse YES kontratları 1.00$ olur, gerçekleşmezse 0.00$
- Fiyat ile gerçek olasılık arasındaki fark → **alım fırsatı**

```mermaid
graph LR
    A[Soru: X olacak mı?] --> B{Piyasa Fiyatı}
    B -->|YES = 0.70$| C[%70 olasılık]
    B -->|NO = 0.30$| D[%30 olasılık]
    C --> E{Olay Gerçekleşti mi?}
    D --> E
    E -->|Evet| F[YES → 1.00$]
    E -->|Hayır| G[NO → 1.00$]
```

**Polymarket** en büyük merkeziyetsiz tahmin piyasasıdır. API aracılığıyla tüm marketlere ve fiyat verilerine erişilebilir.

---

## 2. Kelly Criterion (Kelly Kriteri)

Kelly Criterion, bir bahiste optimal pozisyon büyüklüğünü belirleyen matematiksel formüldür. Amacı, uzun vadede portföy büyümesini maksimize etmektir.

### Formül

$$f^* = \frac{p \cdot b - q}{b}$$

Burada:
- $f^*$ = Sermayenin yüzde kaçının yatırılacağı (Kelly fraction)
- $p$ = Kazanma olasılığı (bizim tahminimiz)
- $q = 1 - p$ = Kaybetme olasılığı
- $b$ = Net oran (odds) = piyasa fiyatından hesaplanan oran

### Örnek
- Bizim tahmimiz: %80 olasılıkla YES
- Piyasa fiyatı: YES = 0.70$ (yani piyasa %70 diyor)
- $b = \frac{1}{0.70} - 1 = 0.4286$
- $f^* = \frac{0.80 \times 0.4286 - 0.20}{0.4286} = \frac{0.1429}{0.4286} = 0.333$
- **Yorum:** Sermayenin %33.3'ü bu fırsata ayrılmalı

**Dikkat:** Kelly fraction negatifse, bu pozisyona girmemek gerekir (edge yok).

Bizim sistemde Kelly fraction'ı **sinyal gücü** olarak kullanıyoruz — gerçekten bahis yapmıyoruz, ama yüksek Kelly = güçlü fırsat demek.

---

## 3. Brier Score (Brier Skoru)

Brier Score, olasılık tahminlerinin kalitesini ölçen bir metriktir. 0 (mükemmel) ile 1 (en kötü) arasında değer alır.

### Formül

$$BS = \frac{1}{N} \sum_{t=1}^{N} (f_t - o_t)^2$$

Burada:
- $f_t$ = t zamanındaki tahmin edilen olasılık
- $o_t$ = Gerçekleşen sonuç (1 = doğru, 0 = yanlış)
- $N$ = Toplam tahmin sayısı

### Yorum Tablosu

| Brier Score | Kalite |
|-------------|--------|
| 0.00 - 0.10 | Mükemmel |
| 0.10 - 0.20 | İyi |
| 0.20 - 0.30 | Orta |
| 0.30+ | Zayıf |

### Örnek
- Tahminimiz: %80 olasılıkla YES → f = 0.80
- Sonuç: YES gerçekleşti → o = 1
- $BS = (0.80 - 1.00)^2 = 0.04$ → Çok iyi!
- Tahminimiz: %80 olasılıkla YES ama NO gerçekleşti → o = 0
- $BS = (0.80 - 0.00)^2 = 0.64$ → Kötü tahmin

---

## 4. Kalibrasyon (Calibration)

Kalibrasyon, tahmin edilen olasılıkların gerçek sonuçlarla ne kadar uyumlu olduğunu ölçer.

**İdeal kalibrasyon:** "%70 dediğimde, gerçekten %70 oranında doğru çıkmalı."

```mermaid
graph TD
    A[Tahminleri bucketa ayır] --> B["%70-80 bucket: 15 tahmin"]
    B --> C{"Kaç tanesi doğru?"}
    C -->|11/15 = %73| D["✅ İyi kalibre (beklenen: %75)"]
    C -->|14/15 = %93| E["⚠️ Overconfident değil, underconfident<br/>(daha yüksek olasılık vermeli)"]
    C -->|7/15 = %47| F["❌ Overconfident<br/>(çok yüksek olasılık veriyor)"]
```

**Overconfident:** Tahmin edilen olasılık, gerçekleşme oranından yüksek  
**Underconfident:** Tahmin edilen olasılık, gerçekleşme oranından düşük

Self-improvement modülümüz, kalibrasyon hatasını izleyerek otomatik düzeltme yapar.

---

## 5. Sentiment Analizi (Duygu Analizi)

Sentiment analizi, metin (haber başlıkları) üzerinden olumlu/olumsuz duygu tespiti yapar.

### Çalışma Prensibi

```mermaid
flowchart TD
    A[Market Sorusu] --> B[Anahtar Kelime Çıkarma]
    B --> C[RSS Feed'lerden Haber Çekme]
    C --> D["Google News (3 feed)"]
    D --> E[Başlık Eşleştirme]
    E --> F{Eşleşen Haber Var mı?}
    F -->|Evet| G[Lexicon-Based Skorlama]
    F -->|Hayır| H[Sentiment = 0 nötr]
    G --> I{Taraf Kontrolü}
    I -->|YES pozisyonu| J[Pozitif haber → skor artar]
    I -->|NO pozisyonu| K[Negatif haber → skor artar]
    J --> L[Final Sentiment Score]
    K --> L
```

### Lexicon (Kelime Sözlüğü) Yaklaşımı
- **Pozitif kelimeler:** "approve", "pass", "win", "agree", "success", "increase" → +1
- **Negatif kelimeler:** "reject", "fail", "lose", "deny", "decrease", "block" → -1
- **Amplifier:** "very", "strongly", "significantly" → skoru 1.5x çarpar
- **Negation:** "not", "no", "never" → skoru tersine çevirir

### YES/NO Taraf Kontrolü
Kritik bir detay: Sentiment skoru, bahsin tarafına göre yorumlanır.
- Eğer **YES** pozisyonundaysak → pozitif haber bizi destekler
- Eğer **NO** pozisyonundaysak → negatif haber bizi destekler

---

## 6. Zaman Serisi Analizi

Market fiyat verilerini analiz etmek için kullandığımız istatistiksel göstergeler.

### 6.1 SMA (Simple Moving Average — Basit Hareketli Ortalama)

$$SMA_n = \frac{1}{n} \sum_{i=0}^{n-1} P_{t-i}$$

Son n günün fiyat ortalaması. Trend yönünü gösterir.
- Fiyat > SMA → Yukarı trend
- Fiyat < SMA → Aşağı trend

**Kullandığımız pencereler:** SMA-3 (kısa), SMA-7 (orta), SMA-14 (uzun)

### 6.2 Volatilite (Oynaklık)

$$\sigma = \sqrt{\frac{1}{n-1} \sum_{i=1}^{n} (r_i - \bar{r})^2}$$

Burada $r_i$ günlük getiri (fiyat değişim yüzdesi). Yüksek volatilite = fiyat çok oynuyor = daha riskli ama daha çok fırsat.

### 6.3 Momentum

$$M = P_t - P_{t-k}$$

Son k gündeki fiyat değişimi. Pozitif momentum = fiyat yükseliyor, negatif = düşüyor.

### 6.4 Z-Score

$$z = \frac{P_t - \mu}{\sigma}$$

Fiyatın ortalamadan kaç standart sapma uzakta olduğu.
- $|z| > 2$ → Fiyat uç noktada, mean reversion olasılığı yüksek
- $|z| < 0.5$ → Fiyat ortalamaya yakın, güçlü sinyal yok

---

## 7. Mean Reversion (Ortalamaya Dönüş)

Mean reversion, fiyatların uzun vadeli ortalamalarına dönme eğiliminde olduğunu söyleyen teori.

```mermaid
graph LR
    A["Fiyat yükseldi<br/>z > +2"] --> B["Aşırı satın alınmış<br/>(Overbought)"]
    B --> C["Düşüş beklenir"]
    D["Fiyat düştü<br/>z < -2"] --> E["Aşırı satılmış<br/>(Oversold)"]
    E --> F["Yükseliş beklenir"]
    G["Fiyat ortalamada<br/>z ≈ 0"] --> H["Güçlü sinyal yok"]
```

**Bizim kullanımımız:**
- z-score hesapla → aşırı yüksek/düşük fiyatlarda sinyal üret
- Mean reversion signal'i statistical score'a katkıda bulunur

---

## 8. Arbitraj ve Spread Anomali

### Spread Nedir?
Bir market'in YES ve NO kontratlarının midpoint fiyatları toplamı teorik olarak 1.00 olmalıdır.

$$\text{Spread} = |P_{YES} + P_{NO} - 1.00|$$

- Spread > 0 → arbitraj fırsatı (her iki tarafı da alıp risksiz kazanç)
- Gerçekte spread genellikle çok küçüktür (0.01-0.05)

### Anomali Tespiti
Spread belirli bir eşiğin üzerindeyse (config'de tanımlı), bu bir **spread anomali** olarak işaretlenir.

```mermaid
graph TD
    A[Market Token ID] --> B[CLOB API: Midpoint]
    B --> C["YES midpoint + NO midpoint"]
    C --> D{Toplam ≠ 1.00?}
    D -->|Spread > eşik| E["✅ Anomali tespit edildi"]
    D -->|Spread ≤ eşik| F["Normal spread"]
    E --> G[Arbitrage Score hesapla]
    G --> H[Kelly Fraction hesapla]
```

---

## 9. Composite Scoring (Bileşik Puanlama)

Her market fırsatı için 4 farklı sinyali ağırlıklı olarak birleştiriyoruz:

$$S_{composite} = w_1 \cdot S_{statistical} + w_2 \cdot S_{sentiment} + w_3 \cdot S_{arbitrage} + w_4 \cdot S_{volume}$$

```mermaid
pie title Varsayılan Scoring Ağırlıkları
    "İstatistiksel (0.40)" : 40
    "Sentiment (0.20)" : 20
    "Arbitraj (0.25)" : 25
    "Hacim (0.15)" : 15
```

| Sinyal | Açıklama | Ağırlık |
|--------|----------|---------|
| Statistical | SMA trend, momentum, z-score, mean reversion | 0.40 |
| Sentiment | RSS haber duygu skoru | 0.20 |
| Arbitrage | Spread anomali tespiti | 0.25 |
| Volume | İşlem hacmi normalize skoru | 0.15 |

Self-improvement modülü bu ağırlıkları otomatik olarak ayarlayabilir.

---

## 10. Self-Improvement (Kendini İyileştirme) Döngüsü

Sistem her çalıştığında, geçmiş tahminlerin doğruluğunu kontrol eder ve parametreleri otomatik ayarlar.

```mermaid
flowchart TD
    A[Pipeline Başla] --> B[Geçmiş Tahminleri Kontrol Et]
    B --> C{Yeterli Veri Var mı?<br/>n ≥ 10}
    C -->|Hayır| D[Ayarlama Yapma]
    C -->|Evet| E[Accuracy Metrikleri Hesapla]
    E --> F{Hit Rate < %65?}
    F -->|Hayır| G[Parametreler İyi, Devam Et]
    F -->|Evet| H[Config Parametrelerini Ayarla]
    H --> I["• Scoring ağırlıkları<br/>• Probability eşikleri<br/>• Volume filtreleri<br/>• SMA pencereleri"]
    I --> J{GitHub Token Var mı?}
    J -->|Evet| K["Copilot API'den Öneri Al<br/>(maks 3 çağrı/gün)"]
    J -->|Hayır| L[Sadece Kural Tabanlı Ayar]
    K --> M[Değişiklikleri Logla]
    L --> M
    M --> N[Güncellenmiş Config ile Devam]
```

### Kural Tabanlı Ayarlar
1. **Kalibrasyon hatası > 0.20** → Sentiment ağırlığını düşür (en gürültülü sinyal)
2. **Hit rate çok düşük** → min_prob eşiğini yükselt (daha seçici ol)
3. **Çok fazla düşük kaliteli sinyal** → min_volume artır
4. **Hit rate çok yüksek** → min_prob eşiğini düşür (daha fazla fırsat bul)
5. **Brier score > 0.30** → Daha uzun SMA penceresi ekle (daha fazla smoothing)

---

## 11. Pipeline Akış Diyagramı

Tüm sistemin uçtan uca akışı:

```mermaid
flowchart TD
    subgraph "Günlük Pipeline (19:00 UTC)"
        A["1. Config Yükle<br/>data/config.json"] --> B["2. Geçmiş Tahminleri Kontrol Et<br/>data/predictions/*.json"]
        B --> C["3. Self-Improvement<br/>Config otomatik ayarla"]
        C --> D["4. Market Tarama<br/>Gamma API → 50,000+ market"]
        D --> E["5. İstatistiksel Analiz<br/>SMA, volatilite, momentum, z-score"]
        E --> F["6. Sentiment Analizi<br/>Google News RSS"]
        F --> G["7. Arbitraj Tespiti<br/>CLOB API spread kontrolü"]
        G --> H["8. Tahmin Oluştur & Rapor"]
    end

    subgraph "Çıktılar"
        H --> I["data/predictions/YYYY-MM-DD.json"]
        H --> J["data/reports/YYYY-MM-DD.html"]
        H --> K["E-posta Gönder (SendGrid)"]
    end

    subgraph "Veri Depolama"
        I --> L["data/history/price_history.json"]
        C --> M["data/history/improvements.jsonl"]
        B --> N["data/predictions/accuracy_log.json"]
    end
```

---

## 12. Gürültü Filtreleme

Polymarket'te 50,000+ market bulunur. Bunların büyük çoğunluğu spor bahisleri, kripto fiyat tahminleri veya tweet sayacı gibi analiz değeri düşük marketlerdir. Filtre sistemi:

```mermaid
flowchart LR
    A["50,000+ Market"] --> B["Olasılık Filtresi<br/>0.70 ≤ p ≤ 0.95"]
    B --> C["Volume Filtresi<br/>volume ≥ $5,000"]
    C --> D["Süre Filtresi<br/>≤ 7 gün kala"]
    D --> E["Regex Gürültü Filtresi<br/>Spor, kripto, hava durumu..."]
    E --> F["Slug Prefix Filtresi<br/>epl-, nba-, cs2-..."]
    F --> G["~30-50 Kaliteli Fırsat"]
```

---

*Bu doküman, sistemin tüm kavramsal temellerini anlamak için hazırlanmıştır. Teknik implementasyon detayları için kaynak koduna bakınız.*

*Son güncelleme: 2026-03-31*
