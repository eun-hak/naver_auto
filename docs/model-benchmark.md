# LLM 모델 성능 벤치마크 (블로그 글쓰기)

> 측정일: 2026-05-31 (UTC)  
> 원본 데이터: [`scripts/full_model_benchmark_results.json`](../scripts/full_model_benchmark_results.json)  
> 재현: `python scripts/full_model_benchmark.py`

naver_auto 파이프라인에서 사용·검토 중인 **Groq 4종, Gemini 2종, Gemma 4 2종, NVIDIA NIM 6종** (총 14모델)을 동일 프롬프트로 비교했습니다.

---

## 1. 테스트 방법

### 공통 조건

| 항목 | 값 |
|------|-----|
| 키워드 | `제주도 맛집` |
| temperature | basic 0.3 / title·body 0.6~0.7 |
| Groq Qwen3 | `reasoning_format: hidden` 적용 |
| NVIDIA | `temperature=1` 미사용, `top_p=0.95` |

### 테스트 4종

| ID | 설명 | max_tokens |
|----|------|------------|
| `basic` | "안녕하세요"만 출력 | 64 |
| `blog_title` | SEO 제목 3개 JSON 배열 | 400 |
| `blog_body_300` | 본문 300자, 마크다운 없음 | 800 |
| `blog_body_1500` | H1 + ## 2섹션 + 마무리, 1500~2000자 | 2500 |

### 점수 산정 (블로그 적합도, 만점 약 70점)

- **basic**: 응답 있고 reasoning-only 아니면 10점
- **blog_title**: JSON 파싱 가능 + 한국어 비율 + 속도
- **blog_body_300**: 200~500자면 가점, 한국어 비율, 속도
- **blog_body_1500**: 1200~2500자면 가점, 한국어 비율, 속도
- reasoning-only·영어 위주 출력·JSON 실패 시 감점

---

## 2. 대상 모델 목록

### Groq (4)

| 모델 ID | 역할 | 코드 내 상수 |
|---------|------|-------------|
| `llama-3.1-8b-instant` | 빠른 작업 | `MODEL_FAST` |
| `qwen/qwen3-32b` | 본문 초안 | `MODEL_DRAFT` |
| `llama-3.3-70b-versatile` | 고품질 | `MODEL_QUALITY` |
| `meta-llama/llama-4-scout-17b-16e-instruct` | Llama 4 Scout | (신규 후보) |

### Gemini API (4)

| 모델 ID | 비고 |
|---------|------|
| `gemini-2.5-flash-lite` | Flash Lite 2.5 |
| `gemini-3.1-flash-lite` | **현재 fast 기본값** |
| `gemma-4-26b-a4b-it` | **현재 body 기본값** |
| `gemma-4-31b-it` | Gemma 4 31B (Gemini API) |

### NVIDIA NIM (6)

| 모델 ID | 비고 |
|---------|------|
| `meta/llama-4-maverick-17b-128e-instruct` | 속도·품질 균형 |
| `meta/llama-3.1-8b-instruct` | 초고속 |
| `meta/llama-3.3-70b-instruct` | 70B instruct |
| `google/gemma-4-31b-it` | Gemma 4 (NIM) |
| `qwen/qwen3-next-80b-a3b-instruct` | Qwen3 Next |
| `meta/llama-3.1-70b-instruct` | 70B (구버전) |

---

## 3. 종합 순위

| 순위 | 제공자 | 모델 | 총점 | 평균 |
|------|--------|------|------|------|
| 1 | Gemini | **Gemini 3.1 Flash Lite** | **66.8** | 16.7 |
| 2 | Groq | Llama 4 Scout 17B | 63.8 | 15.9 |
| 3 | NVIDIA | Qwen3 Next 80B | 62.8 | 15.7 |
| 4 | NVIDIA | Llama 4 Maverick 17B | 59.5 | 14.9 |
| 5 | NVIDIA | Llama 3.1 8B Instruct | 59.4 | 14.9 |
| 6 | NVIDIA | Gemma 4 31B (NIM) | 58.0 | 14.5 |
| 7 | NVIDIA | Llama 3.3 70B Instruct | 57.4 | 14.4 |
| 8 | Groq | Llama 3.3 70B Versatile | 56.6 | 14.1 |
| 9 | Gemini | Gemini 2.5 Flash Lite | 54.7 | 13.7 |
| 10 | Groq | Llama 3.1 8B Instant | 52.8 | 13.2 |
| 11 | NVIDIA | Llama 3.1 70B Instruct | 52.6 | 13.2 |
| 12 | Groq | Qwen3 32B | 41.7 | 10.4 |
| 13 | Gemini | Gemma 4 26B | 21.2 | 5.3 |
| 14 | Gemini | Gemma 4 31B | 16.2 | 4.1 |

---

## 4. 제공자별 상세 결과

### 4.1 Groq

| 모델 | basic | title | body 300 | body 1500 | 총 시간 | 총점 |
|------|-------|-------|----------|-----------|---------|------|
| Llama 4 Scout 17B | 0.6s ✅ | 0.7s ✅ | 1.2s / 485자 | 1.9s / **1167자** | **4.4s** | **63.8** |
| Llama 3.3 70B | 0.7s ✅ | 1.0s ✅ | 2.4s / 535자 | 2.5s / 652자 | 6.5s | 56.6 |
| Llama 3.1 8B | 3.4s ✅ | 0.8s ✅ | 1.8s / 808자 | 2.5s / 707자 | 8.5s | 52.8 |
| Qwen3 32B | 0.7s ❌ 빈응답 | 4.2s ❌ 빈응답 | 1.7s / 249자 | 5.4s / 1096자 | 12.0s | 41.7 |

**Groq 요약**

- **Llama 4 Scout**: 속도·품질·분량 모두 우수. Groq 4종 중 **블로그 최적**.
- **Qwen3 32B**: reasoning 토큰이 `max_tokens`를 소진해 basic·title이 **빈 응답**. 본문만 쓸 때는 가능하나 현재 `MODEL_DRAFT`로는 부적합.
- Groq 무료 한도: Developer Plan 기준 모델별 **~1K RPM, 250~300K TPM** ([Groq Docs](https://console.groq.com/docs/models)).

---

### 4.2 Gemini API

| 모델 | basic | title | body 300 | body 1500 | 총 시간 | 총점 |
|------|-------|-------|----------|-----------|---------|------|
| **Gemini 3.1 Flash Lite** | 1.4s ✅ | 1.2s ✅ | 5.4s / **304자** | 5.1s / **1623자** | 13.1s | **66.8** |
| Gemini 2.5 Flash Lite | 2.7s ✅ | 1.6s ✅ | 3.1s / 579자 | 13.6s / 3851자 | 21.0s | 54.7 |
| Gemma 4 26B | 2.4s ⚠️ | 9.5s ⚠️ | 17.9s ⚠️ | 49.2s ⚠️ | 79.0s | 21.2 |
| Gemma 4 31B | 5.3s ⚠️ | 12.5s ⚠️ | 27.8s ⚠️ | 56.7s ⚠️ | 102.3s | 16.2 |

**Gemini 요약**

- **Gemini 3.1 Flash Lite**: 제목·본문(300·1500) **분량 준수·한국어 품질** 모두 1위. 현재 fast 모델 유지 권장.
- **Gemma 4 26B / 31B (Gemini API)**: 응답에 **영어 추론·메타 설명**이 섞여 출력됨 (`* Input: ...`, `Jeju Island Restaurants` 등). naver_auto의 system 프롬프트 없이 raw 호출 시 **블로그용 부적합**.
  - 프로덕션에서는 `gemini_client.py`의 system 지시가 있어 실제 품질은 개선될 수 있으나, 이번 벤치마크 기준으로는 **NIM `google/gemma-4-31b-it`가 훨씬 낫다**.
- Gemini 무료: body/fast **20 RPM** (코드 기본값).

---

### 4.3 NVIDIA NIM

| 모델 | basic | title | body 300 | body 1500 | 총 시간 | 총점 |
|------|-------|-------|----------|-----------|---------|------|
| Qwen3 Next 80B | 3.5s ✅ | 3.3s ✅ | 7.0s / 242자 | 21.7s / 1363자 | 35.5s | 62.8 |
| Llama 4 Maverick 17B | 0.6s ✅ | 1.5s ✅ | 2.9s / 243자 | 7.0s / 652자 | 12.0s | 59.5 |
| Llama 3.1 8B | 0.6s ✅ | 0.9s ✅ | 3.7s / 670자 | 3.7s / 1091자 | 8.9s | 59.4 |
| Gemma 4 31B (NIM) | 75.9s ✅ | 24.8s ✅ | 30.0s / **308자** | 57.0s / **1999자** | 188.7s | 58.0 |
| Llama 3.3 70B | 10.4s ✅ | 1.5s ✅ | 12.3s / 372자 | 18.3s / 731자 | 42.5s | 57.4 |
| Llama 3.1 70B | 1.0s ✅ | 2.4s ✅ | 58.3s / 542자 | 120.8s / 950자 | 182.5s | 52.6 |

**NVIDIA 요약**

- **Llama 4 Maverick / Llama 3.1 8B**: Groq와 비슷한 속도, **무료 백업 LLM**으로 적합.
- **Gemma 4 31B (NIM)**: Gemini API Gemma 대비 **한국어 본문 품질 우수**, 1500자 본문 **1999자**로 목표 충족. 다만 **느림** (본문 2건 ~88초).
- **Qwen3 Next 80B**: SEO 제목·본문 품질 좋음, 중간 속도.
- **Llama 3.1 70B**: 본문 생성 **58~121초**로 느림.
- NVIDIA 무료: **~40 RPM** (모델별 상이), [build.nvidia.com](https://build.nvidia.com) Developer Program.

---

## 5. 역할별 추천 (블로그 파이프라인)

### 제목 · 메타 · 키워드 리서치 (fast)

| 우선순위 | 모델 | 제공자 | 이유 |
|----------|------|--------|------|
| 1 | `gemini-3.1-flash-lite` | Gemini | 총점 1위, SEO 제목·1623자 본문도 우수 |
| 2 | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq | 0.7초 제목, Groq 최고 |
| 3 | `meta/llama-4-maverick-17b-128e-instruct` | NVIDIA | 1.5초, JSON 깔끔, 무료 백업 |

### 본문 1500~3000자 (body)

| 우선순위 | 모델 | 제공자 | 이유 |
|----------|------|--------|------|
| 1 | `gemini-3.1-flash-lite` | Gemini | 5.1초 / 1623자, 분량·한국어 최적 |
| 2 | `google/gemma-4-31b-it` | **NVIDIA NIM** | 57초 / **1999자**, Gemma 계열 중 품질 최고 |
| 3 | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq | 1.9초 / 1167자, **속도 최우선** |
| 4 | `qwen/qwen3-next-80b-a3b-instruct` | NVIDIA | 21.7초 / 1363자, SEO 문체 좋음 |

### Groq / Gemini 장애 시 백업

| 역할 | 추천 |
|------|------|
| fast | NVIDIA `meta/llama-4-maverick-17b-128e-instruct` |
| body | NVIDIA `google/gemma-4-31b-it` 또는 `qwen/qwen3-next-80b-a3b-instruct` |

### 사용 비권장

| 모델 | 이유 |
|------|------|
| `minimaxai/minimax-m2.7` (NIM) | reasoning-only, 300자에 211초+ (별도 테스트) |
| `qwen/qwen3-32b` (Groq) | title/basic 빈 응답 (reasoning 토큰 소진) |
| `gemma-4-26b-a4b-it` / `gemma-4-31b-it` (Gemini API) | raw 호출 시 영어 추론 노출 (이번 벤치 하위권) |

---

## 6. naver_auto 현재 설정 vs 권장 변경

### 현재 (`generator.py`)

```
fast  → gemini-3.1-flash-lite   ✅ 유지
body  → gemma-4-26b-a4b-it     ⚠️ Gemini API Gemma는 추론 노출 이슈
fallback → Groq (qwen3-32b 본문) ⚠️ title/basic 실패
```

### 권장 조합 A — 품질 우선 (현재 구조 유지 + 미세 조정)

| 역할 | 모델 | 제공자 |
|------|------|--------|
| research · title · meta | `gemini-3.1-flash-lite` | Gemini |
| body | `gemini-3.1-flash-lite` | Gemini (Gemma 26B 대체 검토) |
| fallback fast | `llama-3.1-8b-instant` | Groq |
| fallback body | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq |

### 권장 조합 B — 비용·한도 분산

| 역할 | 모델 | 제공자 |
|------|------|--------|
| fast | `gemini-3.1-flash-lite` | Gemini |
| body | `google/gemma-4-31b-it` | **NVIDIA NIM** |
| fallback | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq |

### 권장 조합 C — 속도 최우선

| 역할 | 모델 | 제공자 |
|------|------|--------|
| fast | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq |
| body | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq |
| backup | `meta/llama-4-maverick-17b-128e-instruct` | NVIDIA |

---

## 7. 속도 비교 (blog_body_1500 기준)

```
Groq Llama 4 Scout     ████ 1.9s   (1167자)
Groq Llama 3.3 70B     █████ 2.5s  (652자)
Groq Llama 3.1 8B      █████ 2.5s  (707자)
Gemini 3.1 Flash Lite  ██████████ 5.1s  (1623자) ← 품질·속도 균형
NVIDIA Maverick 17B    ██████████████ 7.0s
NVIDIA Llama 3.1 8B    ███████ 3.7s
NVIDIA Qwen3 Next 80B  █████████████████████ 21.7s
NVIDIA Gemma 4 31B     ████████████████████████████████████████████████████████ 57.0s (1999자)
Gemini 2.5 Flash Lite  █████████████ 13.6s
Gemma 4 26B (Gemini)   █████████████████████████████████████████████████ 49.2s
NVIDIA Llama 3.1 70B   ████████████████████████████████████████████████████████████████████████████████████████████████████ 120.8s
```

---

## 8. API 사용량 · 제한 요약

| 제공자 | 무료 | Rate Limit | 프로덕션 |
|--------|------|------------|----------|
| **Groq** | Developer Plan | ~1K RPM, 250~300K TPM | 유료 tier |
| **Gemini** | API 무료 tier | body/fast **20 RPM** (코드 기본) | 유료 |
| **NVIDIA NIM** | build.nvidia.com | **~40 RPM** (모델별) | NIM Enterprise |

---

## 9. 재현 방법

```powershell
cd naver_auto
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -u scripts\full_model_benchmark.py   # 4종 프롬프트 종합
.venv\Scripts\python.exe -u scripts\body_2500_benchmark.py    # 2000~3000자 본문 전용
```

필요 환경변수: `GROQ_API_KEY` (또는 `GROK_API_KEY`), `GEMINI_API_KEY`, `NVIDIA_API_KEY`

---

## 10. 본문 2000~3000자 전용 벤치마크

> 측정일: 2026-05-31 · 원본: [`scripts/body_2500_benchmark_results.json`](../scripts/body_2500_benchmark_results.json)

실제 `groq_client.generate_blog_body` / `gemini_client.generate_blog_body`와 **동일한 system·프롬프트 구조**로, 분량 **2000~3000자**를 요청했습니다.

| 조건 | 값 |
|------|-----|
| 키워드 | `제주도 맛집` |
| H1 | `제주도 맛집 추천 \| 현지인이 알려주는 BEST 10` |
| 구조 | H1 → 도입 2~3문단 → ## 2~3개 → 체크리스트 → FAQ → 해시태그 |
| max_tokens | 4096 |
| temperature | 0.6 |

### 10.1 종합 순위 (2000~3000자)

| 순위 | 제공자 | 모델 | 점수 | 글자수 | 목표 충족 | 소요 |
|------|--------|------|------|--------|-----------|------|
| 1 | Gemini | **Gemini 3.1 Flash Lite** | **39.5** | **2380** | ✅ | **7.4s** |
| 2 | NVIDIA | Llama 3.1 8B Instruct | 39.4 | 2155 | ✅ | 9.3s |
| 3 | Groq | Llama 3.1 8B Instant | 39.3 | 2155 | ✅ | 11.1s |
| 4 | NVIDIA | Qwen3 Next 80B | 37.9 | 2079 | ✅ | 31.4s |
| 5 | Groq | Qwen3 32B | 32.4 | 1919 | ❌ (약 80자 부족) | 8.3s |
| 6 | NVIDIA | Gemma 4 31B (NIM) | 30.7 | 3055 | ❌ (55자 초과) | 63.8s |
| 7 | NVIDIA | Llama 4 Maverick 17B | 30.3 | 1573 | ❌ | 11.0s |
| 8 | Gemini | Gemini 2.5 Flash Lite | 29.9 | 3787 | ❌ (과다) | 16.0s |
| 9 | Groq | Llama 3.3 70B Versatile | 27.8 | 1182 | ❌ | 3.6s |
| 10 | Groq | Llama 4 Scout 17B | 27.6 | 1403 | ❌ | 2.7s |
| 11 | NVIDIA | Llama 3.1 70B Instruct | 26.6 | 1713 | ❌ | 41.3s |
| 12 | NVIDIA | Llama 3.3 70B Instruct | 24.2 | 1398 | ❌ | 27.3s |
| 13 | Gemini | Gemma 4 31B | 19.9 | 6412 | ❌ | 86.0s |
| 14 | Gemini | Gemma 4 26B | 19.8 | 6899 | ❌ | 69.1s |

**목표 충족 (2000~3000자)**: 4개 모델만 ✅

### 10.2 제공자별 요약

**Gemini**
- `gemini-3.1-flash-lite`: **2000~3000자 본문 1위** — 2380자, 7.4초, H2 4개, 한국어 86%
- `gemini-2.5-flash-lite`: 3787자로 **분량 초과** (품질은 좋음)
- `gemma-4-26b/31b`: 6400~6900자 + 영어 메타 노출 → **부적합**

**Groq**
- `llama-3.1-8b-instant`: 2155자 ✅, Groq 중 **유일하게 목표 충족**
- `qwen3-32b`: system 프롬프트 적용 시 1919자 (거의 충족), 8.3초
- `llama-4-scout`, `llama-3.3-70b`: **1400자 내외로 분량 미달** (속도는 빠름)

**NVIDIA NIM**
- `llama-3.1-8b-instruct`: 2155자 ✅, 9.3초 — Groq 8B와 동급
- `qwen3-next-80b`: 2079자 ✅, 문체 우수, 31초
- `google/gemma-4-31b-it`: 3055자 (약간 초과), **한국어 품질 최고급**이나 64초
- 70B 계열: 1400~1700자로 **분량 미달** 경향

### 10.3 2000~3000자 본문 추천

| 우선순위 | 모델 | 제공자 | 이유 |
|----------|------|--------|------|
| **1 (메인)** | `gemini-3.1-flash-lite` | Gemini | 목표 분량·속도·품질 최적 |
| **2 (Groq)** | `llama-3.1-8b-instant` | Groq | 2155자/11초, 무료 한도 넉넉 |
| **3 (NVIDIA 백업)** | `meta/llama-3.1-8b-instruct` | NVIDIA | Groq와 동일 수준 |
| **4 (품질)** | `qwen/qwen3-next-80b-a3b-instruct` | NVIDIA | 2079자, SEO 문체 우수 |
| **5 (장문·고품질)** | `google/gemma-4-31b-it` | NVIDIA | 3055자, 약간 길지만 문장 품질 최고 |

**주의**: 1500자 테스트에서는 상위였던 **Groq Llama 4 Scout / Llama 3.3 70B**는 2000~3000자 요청 시 **1200~1400자에서 멈춤**. 실제 파이프라인이 2000~3000자면 이 모델들은 단독 body용으로 부적합.

### 10.4 naver_auto body 설정 권장 (2000~3000자 기준)

```
body → gemini-3.1-flash-lite          (1순위, 현재 fast와 동일 모델 가능)
fallback body → llama-3.1-8b-instant  (Groq)
backup body → qwen/qwen3-next-80b     (NVIDIA, 품질 우선)
```

`gemma-4-26b-a4b-it` (Gemini API)는 **2000~3000자에서도 하위권** — body 역할 교체 권장.

---

## 11. 결론

1. **종합 1위는 `gemini-3.1-flash-lite`** — 제목·본문(300·1500·**2000~3000**) 모두 분량·한국어·속도 균형이 가장 좋다.
2. **2000~3000자 본문**에서 목표 분량을 맞춘 모델은 **4개뿐**: Gemini 3.1 Flash Lite, Groq/NVIDIA Llama 3.1 8B, NVIDIA Qwen3 Next 80B.
3. **Groq Llama 4 Scout / 3.3 70B**는 짧은 본문(1500자)엔 괜찮지만 **2000~3000자 요청 시 1400자 내외에서 종료** — body 단독 사용 비권장.
4. **Gemma 4 26B/31B (Gemini API)**는 분량·품질 모두 하위 — **`gemini-3.1-flash-lite`로 body 교체** 또는 NVIDIA NIM `google/gemma-4-31b-it` 검토.
5. **NVIDIA NIM 백업**으로 `llama-3.1-8b-instruct`, `qwen3-next-80b`가 실용적이다.
6. **MiniMax M2.7 등 reasoning-only 모델은 블로그 자동화에 부적합** (별도 측정, 이 문서 범위 외).
