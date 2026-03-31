# Polymarket Tahmin Sistemi — Araştırma Notları

> Bu dosya, sistemimizi geliştirmek için incelediğim akademik makaleler, strateji araştırmaları ve çıkarılan sonuçları içerir.

---

## 1. Akademik Makaleler

### 1.1 "Approaching Human-Level Forecasting with Language Models" (Halawi et al., 2024)

**arXiv:** 2402.18563  
**Özet:** Retrieval-augmented bir LLM sistemi kullanarak tahmin marketlerinde insan düzeyine yakın performans gösteren bir yaklaşım.

**Anahtar Bulgular:**
- **Pipeline:** Soru → Bilgi Retrieval (web arama) → LLM Tahmin → Ensemble Agregasyon
- Sistem, rekabetçi tahmin platformlarındaki insan crowd aggregate'ine yakın Brier score elde ediyor
- Tek başına LLM tahmini zayıf, ama **bilgi retrieval ile güçlendirilince** performans dramatik artıyor
- Ensemble (çoklu tahmin → median/ortalama) tek tahminden tutarlı olarak daha iyi
- Fine-tuning yapmadan, prompt engineering + retrieval ile güçlü sonuçlar elde edilebiliyor

**Bizim Sisteme Çıkarımlar:**
- ✅ Zaten RSS-based sentiment retrieval yapıyoruz — bu yaklaşımın doğruluğunu teyit ediyor
- 🔮 **Gelecek iyileştirme:** Self-improvement API çağrılarında, market sorusu + ilgili haberler birlikte gönderilmeli (retrieval-augmented prompt)
- 🔮 **Ensemble:** Birden fazla prompt ile tahmin alıp median değer kullanılabilir (ancak premium request bütçesini dikkate almak lazım)
- 🔮 **Search-then-forecast:** Her market için anahtar kelime araması → bulunan haberlerle LLM'e soru sorma pattern'i eklenebilir

### 1.2 "Forecasting Future World Events with Neural Networks" (Zou et al., NeurIPS 2022)

**arXiv:** 2206.15474  
**Özet:** Autocast dataset — zaman serisi tahmin soruları ve ilgili haber korpusu ile gelecek olayları tahmin eden neural network yaklaşımı.

**Anahtar Bulgular:**
- **Autocast Dataset:** ~6,000 gerçek dünya tahmin sorusu (Metaculus, GJOpen vb.)
- Her soru ile birlikte temporal bilgi: açılış tarihi, kapanış tarihi, resolution tarihi
- **News Corpus:** Her soru ile ilişkili haber makaleleri (temporal ordering ile)
- En iyi performans: haber bilgisi + soru metni birlikte kullanıldığında
- Baseline model: calibrated historical frequency + recency weighting
- **Temporal leakage** riski: eğitim verisinde gelecek bilgisi sızmaması gerekiyor

**Bizim Sisteme Çıkarımlar:**
- ✅ Zaten temporal filtre uyguluyoruz (`max_days_left` ile market bitiş tarihi kontrolü)
- 🔮 **Recency weighting:** Haberlerin yayın tarihine göre ağırlıklandırma eklenebilir (yeni haberler → daha yüksek ağırlık)
- 🔮 **Historical frequency baseline:** Benzer soru kategorilerindeki historik resolution oranları referans olarak kullanılabilir
- 🔮 **Market kategorisi analizi:** Politik, ekonomik, bilimsel vb. kategorilerde ayrı kalibrasyon yapılabilir

---

## 2. Prediction Market Stratejileri

### 2.1 Kelly Criterion Optimizasyonu
- **Mevcut:** Kelly fraction hesaplıyoruz (`edge / odds` formülü)
- **Gelişme fırsatı:** Fractional Kelly (Kelly * 0.25-0.50) kullanmak, tam Kelly'den daha stabil. Ama biz bet yapmıyoruz, sinyal olarak kullanıyoruz — bu yüzden mevcut yaklaşım yeterli.
- **Sonuç:** Kelly'yi composite score'da zaten kullanıyoruz, ek bir ayar gerekmez.

### 2.2 Mean Reversion
- **Prensibi:** Fiyat, uzun vadeli ortalamadan sapınca geri dönme eğiliminde
- **Mevcut:** z-score hesaplayıp mean reversion signal'i kullanıyoruz
- **Gelişme fırsatı:** Mean reversion sinyalinin doğruluk oranını izlemek. Eğer bu sinyal tek başına iyi tahmin yapıyorsa, scoring weight'ini artırmak.
- **Half-life analizi:** Mean reversion hızını ölçmek (log-price autocorrelation) — ama stdlib kısıtımız ile karmaşık olabilir.

### 2.3 Cross-Market Arbitrage
- **Prensibi:** Aynı soruyu soran farklı marketlerdeki fiyat farkları
- **Mevcut:** Token YES + token NO midpoint toplamı > 1 veya < 1 ise spread anomali tespit ediyoruz
- **Gelişme fırsatı:**
  - Correlated markets arası fiyat farkı analizi (örn. "X before Y" vs "X happens" vs "Y happens")
  - Conditional probability consistency kontrolü
- **Kısıt:** Polymarket'te çapraz korelasyon verisi almak ekstra API çağrısı gerektiriyor

### 2.4 Liquidity-Weighted Scoring
- **Prensipi:** Düşük likidite marketlerde fiyat daha az güvenilir
- **Mevcut:** Volume ağırlığını kullanıyoruz (scoring weights'da 0.15)
- **Gelişme fırsatı:** Order book depth verisi (CLOB API'den daha detaylı) kullanarak likidite kalitesini ölçmek

### 2.5 Contrarian / Crowd Wisdom Divergence
- **Yeni strateji fikri:** Sentiment analizi ile market fiyatı arasındaki uyumsuzluk
  - Eğer sentiment çok pozitif ama market fiyatı düşük → olası underpriced sinyal
  - Eğer sentiment negatif ama market fiyatı yüksek → olası overpriced sinyal
- **Implementasyon:** `sentiment_score` ile `predicted_prob` arasındaki farkı ölçen ek bir sinyal
- **Risk:** Contrarian strateji bazı durumlarda "piyasa haklıdır" prensibine aykırı olabilir

---

## 3. Premium Request Bütçe Stratejisi

### 3.1 Mevcut Durum
- **Toplam bütçe:** 500 premium request/ay
- **Günlük çalışma:** 1 pipeline run/gün
- **Maks çağrı/run:** 3 (config'de sabit)
- **Hesap:** 500 / 3 = ~166 gün → ~5.5 ay (aylık yenileme ile yeterli)

### 3.2 Çağrı Tetikleme Koşulları
Self-improvement API çağrıları **sadece** şu koşulda yapılıyor:
- `total_predictions >= 10` VE `hit_rate < accuracy_target (0.65)`
- Yani performans yeterli olduğunda çağrı yapılmıyor → bütçe korunuyor

### 3.3 Optimizasyon Stratejileri
1. **Adaptive çağrı sayısı:** Performans çok düşükse (hit_rate < 0.40) → 3 çağrı, orta (0.40-0.60) → 2, hafif düşük (0.60-0.65) → 1
2. **Haftalık özet:** Her gün çağırmak yerine, haftalık performans özeti ile tek seferde daha kapsamlı analiz
3. **Cache:** Benzer metrikler için önceki yanıtları tekrar kullanma (improvements.jsonl'den)
4. **Seasonal budgeting:** Ay sonuna yaklaşırken kalan bütçeyi kontrol et

### 3.4 En Değerli API Kullanım Senaryoları (öncelik sırası)
1. **Accuracy düşüşü tespiti:** Brier score aniden yükseldiğinde kök neden analizi
2. **Kalibrasyon düzeltme:** Belirli olasılık aralığında sistematik bias varsa
3. **Yeni pattern keşfi:** Yanlış tahminlerde ortak pattern varsa

---

## 4. Potansiyel Yeni Taktikler

### 4.1 LLM-Based Market Resolution Prediction
- Her market için LLM'e "Bu market YES mi NO mu resolve olacak?" sorusu sorulabilir
- **Maliyet:** Market başına 1 API çağrısı → çok pahalı (32 market × 1 çağrı = 32/gün)
- **Alternatif:** Sadece en yüksek scorlu 3-5 market için LLM onayı almak
- **Implementasyon:** `predictor.py`'de top-N prediction'lar için LLM doğrulama adımı

### 4.2 Few-Shot Örneklerle Tahmin
- Geçmiş doğru tahminleri few-shot örnek olarak LLM prompt'una eklemek
- "Şu market doğru tahmin ettim, benzer pattern'deki şu yeni market için ne dersin?"
- **Kısıt:** Prompt uzunluğu ve token limiti (max_tokens: 300)

### 4.3 Cross-Platform Spread Detection
- Polymarket vs diğer tahmin platformları (Metaculus, Manifold) arasında fiyat karşılaştırması
- **Kısıt:** Diğer platformların API'leri farklı, stdlib ile erişim zor olabilir
- **Alternatif:** Google News araması ile "X platform predicts Y" haberleri yakalamak

---

## 5. Sonuç ve Yol Haritası

### Kısa Vadeli (1-2 hafta)
- [x] JS column sorting raporda tüm tablolara eklendi
- [x] Self-improvement promptları iyileştirildi (stratejik, kalibrasyon, error pattern)
- [ ] Accuracy izleme: ilk 10 tahmin sonrası kalibrasyon raporu

### Orta Vadeli (1-2 ay)
- [ ] Recency-weighted sentiment (haber yaşına göre ağırlık)
- [ ] Adaptive API çağrı sayısı (performansa göre 1-3)
- [ ] Market kategorisi bazlı ayrı kalibrasyon

### Uzun Vadeli (3+ ay)
- [ ] Top-N market LLM doğrulaması (premium request ile)
- [ ] Cross-platform fiyat karşılaştırması
- [ ] Historical resolution frequency baseline

---

*Son güncelleme: 2026-03-31*
