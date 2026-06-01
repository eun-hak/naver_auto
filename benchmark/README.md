# LLM 모델 벤치마크 (참고용)

네이버 블로그 자동화 본체와 분리해 둔 **모델 선정·비교 테스트** 산출물입니다.

## 구조

```
benchmark/
  model-benchmark.md   # 종합 결론·순위
  scripts/             # 재현용 벤치 스크립트
  results/             # JSON 결과
  samples/             # 생성 본문 샘플 (.md)
  logs/                # 콘솔 로그 (참고용)
```

## 재현

```bash
cd naver_auto
uv run python benchmark/scripts/full_model_benchmark.py
uv run python benchmark/scripts/body_2500_benchmark.py
```

환경변수: `GEMINI_API_KEY`, `GROQ_API_KEY`, `NVIDIA_API_KEY`

## 프로덕션 모델 (2026-06)

| 역할 | 모델 | 제공자 |
|------|------|--------|
| 블로그 메인 | `gemini-3.1-flash-lite` | Gemini |
| 대량 1순위 | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq (1,000 RPD) |
| 대량 백업 (속도) | `meta/llama-3.1-8b-instruct` | NVIDIA NIM |
| 대량 백업 (완결) | `mistralai/mistral-nemotron` | NVIDIA NIM |

자세한 근거: [model-benchmark.md](model-benchmark.md)
