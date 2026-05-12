# AI 재무 컨설팅 어시스턴트

LangGraph Supervisor 멀티에이전트 파이프라인으로 DART에서 상장 기업 재무 데이터를 가져오고, Claude AI가 분석한 결과를 Streamlit 대시보드와 한글 PDF 리포트로 제공합니다.

> SDIC AI Team 1 | Week 3

---

## 기술 스택

| 역할 | 라이브러리 |
|------|-----------|
| 에이전트 오케스트레이션 | LangGraph |
| LLM | Claude (Anthropic) |
| 재무 데이터 | DART Open API (`dart-fss`) |
| UI | Streamlit |
| PDF 생성 | fpdf2 + NanumGothic |

---

## 폴더 구조

```
sdic-ai-team1/
├── app.py                      # Streamlit UI 진입점
├── graph.py                    # LangGraph StateGraph (Supervisor 패턴)
├── data.py                     # DART API 연동 및 재무 데이터 파싱
├── claude_client.py            # Anthropic API 래퍼
├── report.py                   # (레거시) 리포트 유틸
├── agents/
│   ├── __init__.py
│   ├── data_agent.py           # DART 데이터 수집 노드
│   ├── analysis_agent.py       # Claude 재무 분석 노드
│   └── report_agent.py         # 한글 PDF 생성 노드
└── fonts/
    └── NanumGothic.ttf         # 한글 PDF 폰트
```

---

## 설치

```bash
pip install -r requirements.txt
```

프로젝트 루트에 `.env` 파일을 생성하고 아래 두 키를 입력합니다.

```
DART_API_KEY=your_dart_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
```

- DART API 키 발급: https://opendart.fss.or.kr
- Anthropic API 키 발급: https://console.anthropic.com

---

## 실행

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 로 접속합니다.

---

## 5분 시연 시나리오

### 팀별 배정 기업

| 팀 | 기업 |
|----|------|
| Team 1 | 에이피알 |
| Team 2 | 삼성전자 |
| Team 3 | LG 이노텍 |

---

### Case 1. 본인 팀 배정 기업 (정상 케이스)

기업명 입력 후 **분석 시작** 클릭.

- 사이드바: Data Agent / Analysis Agent / Report Agent 모두 **완료**
- 탭 1 (재무 데이터): 5개년 재무 현황 표 (매출액 / 영업이익 / 순이익, 단위 억원)
- 탭 2 (Claude 분석): 영업이익률 언급으로 시작하는 한국어 3~5문장 분석
- 탭 2 하단: **PDF 다운로드** 버튼 클릭 시 한글 PDF 저장, 화면 유지

---

### Case 2. 카카오 (IT 업종 레이블 검증)

`카카오` 입력 후 분석.

- DART에서 `영업수익` 레이블을 `매출액`으로 정상 매핑
- `당기순이익(손실)` 레이블 파싱 (2023~2024년 순이익 음수)
- Case 1과 동일하게 표 / 분석 / PDF 정상 출력

---

### Case 3. asdfasdf (잘못된 회사명)

`asdfasdf` 입력 후 분석.

- 사이드바: Data Agent **완료**, Analysis Agent / Report Agent **오류**
- 메인 화면: `데이터를 찾을 수 없습니다` 에러 메시지
- 앱 크래시 없음

---

## Week 4 예고

- SQLite 캐시: 동일 기업 재조회 시 DART 호출 없이 즉시 반환
- RAG + Text2SQL: 자연어로 재무 데이터 질의
- Streamlit Cloud 배포: 공개 URL로 팀 외부 공유 가능
