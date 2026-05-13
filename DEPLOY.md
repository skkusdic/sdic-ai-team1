# 배포 가이드 — Streamlit Cloud

## 순서

### 1. GitHub에 푸시
```bash
git pull --rebase origin main
git push origin main
```

### 2. Streamlit Cloud 연결
1. [share.streamlit.io](https://share.streamlit.io) 접속 → **Sign in with GitHub**
2. **New app** 클릭
3. 설정:
   | 항목 | 값 |
   |---|---|
   | Repository | `skkusdic/sdic-ai-team1` |
   | Branch | `main` |
   | Main file path | `app.py` |
4. **Deploy** 클릭

### 3. Secrets 등록 (필수 — 없으면 API 오류)
1. 배포 후 앱 대시보드 → **⋮ (더보기)** → **Settings** → **Secrets**
2. 아래 내용 붙여넣기 (실제 키로 교체):
```toml
DART_API_KEY = "실제_DART_API_키"
ANTHROPIC_API_KEY = "실제_ANTHROPIC_API_키"
```
3. **Save** → 앱 자동 재시작

### 4. 첫 배포 확인
- 앱 URL: `https://<앱이름>.streamlit.app`
- 사이드바 **SQLite 캐시** 항목이 비어있는 것이 정상 (배포 환경은 DB 초기화됨)
- **에이피알** 검색 → 분석 결과 확인

---

## 로컬 개발 환경

```bash
# 패키지 설치
pip install -r requirements.txt

# .env 파일 생성 (로컬용, 절대 커밋 금지)
cp .streamlit/secrets.toml.example .env
# .env 파일 열어서 실제 키 입력

# 앱 실행
streamlit run app.py
```

## 주의사항

- `.streamlit/secrets.toml` 은 `.gitignore`에 등록되어 있어 커밋되지 않음
- `data/` 폴더와 `*.db` 파일도 커밋 제외 — Streamlit Cloud는 매 배포마다 초기화
- API 키는 Streamlit Cloud Secrets 또는 로컬 `.env` 에만 보관
