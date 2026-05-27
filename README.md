# naver-auto

키워드 → AI 블로그 초안 생성 → 네이버 임시저장 CLI.

## 설치

```bash
cd naver_auto
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
cp .env.example .env
```

## 사용

```bash
# 초안 생성
naver-auto create --keyword "나는솔로 28기"

# 상태 확인
naver-auto status
naver-auto list

# 네이버 로그인 (최초 1회)
python scripts/login_once.py

# 임시저장
naver-auto publish --draft-id draft_xxx

# draft_ready 초안 일괄 임시저장
naver-auto publish --all --limit 3

# SNS·웹에서 관련 이미지 재수집
naver-auto fetch-images --draft-id draft_xxx --force
```

## 환경 변수

`.env.example` 참고. 필수: `GROQ_API_KEY`, `NAVER_BLOG_ID`. 발행 전 `login_once.py` 실행.
