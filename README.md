# 정책·경제 일정 캘린더

한국은행 금통위, 통계청 지표 발표, 국회 의사일정 등 국내 주요 정책·경제 일정을
한 화면에 모아 달력과 표로 보여주는 정적 사이트.

서버 없이 돌아갑니다. GitHub Actions 가 하루 두 번 일정을 수집해 JSON 으로 커밋하고,
GitHub Pages 가 그 JSON 을 읽는 정적 페이지를 서빙합니다. 운영비는 0원이고,
갱신 이력은 git 커밋 로그로 그대로 남습니다.

설계 배경과 결정 이유는 [DESIGN.md](DESIGN.md)를 보세요.

---

## 설치

### 1. 저장소 준비

```bash
git init && git add . && git commit -m "초기 커밋"
gh repo create kr-policy-calendar --public --source=. --push
```

### 2. GitHub Pages 켜기

저장소 **Settings → Pages** 에서
- Source: `Deploy from a branch`
- Branch: `main` / 폴더 `/docs`

몇 분 뒤 `https://<계정>.github.io/kr-policy-calendar/` 에서 열립니다.

### 3. Actions 쓰기 권한 켜기

**Settings → Actions → General → Workflow permissions** 에서
`Read and write permissions` 를 선택합니다. 봇이 수집 결과를 커밋해야 합니다.

### 4. API 키 등록 (선택)

**Settings → Secrets and variables → Actions** 에 등록합니다.
없어도 동작하며, 해당 소스만 건너뜁니다.

| 이름 | 발급처 | 용도 |
|---|---|---|
| `ASSEMBLY_API_KEY` | https://open.assembly.go.kr | 국회 의사일정 |
| `DATA_GO_KR_KEY` | https://www.data.go.kr (특일 정보) | 공휴일·증시 휴장일 |

### 5. 첫 수집

**Actions → 일정 수집 → Run workflow**. 소스 입력란을 비우면 전체를 수집합니다.

---

## 사용

### 수동 갱신
Actions 탭에서 `Run workflow`. 특정 소스만 다시 긁고 싶으면 입력란에 `bok assembly` 처럼 ID 를 공백으로 구분해 넣습니다.

### 자동 갱신
매일 07:00, 19:00 (KST). 주기는 `.github/workflows/collect.yml` 의 cron 을 고치면 됩니다.
GitHub 의 예약 실행은 부하에 따라 수십 분 늦을 수 있습니다. 정시 실행이 필요한 용도에는 적합하지 않습니다.

### 일정 직접 넣기
`docs/data/manual.json` 을 편집하고 커밋하면 끝입니다. 웹에서 바로 편집해도 됩니다.

```json
{
  "events": [
    {
      "title": "금융통화위원회 (통화정책방향)",
      "category": "MONETARY",
      "agency": "한국은행",
      "date": "2026-08-27",
      "time": "09:00",
      "importance": 3,
      "status": "CONFIRMED",
      "description": "기준금리 결정 및 총재 기자간담회",
      "source_url": "https://www.bok.or.kr/..."
    }
  ]
}
```

여기 넣은 일정은 `locked` 이 기본 `true` 라 자동 수집이 덮어쓰지 않습니다.
자동 수집 값으로 갱신되게 하려면 `"locked": false` 를 명시하세요.

카테고리: `MONETARY` `INDICATOR` `REALESTATE` `FISCAL` `ASSEMBLY` `FINANCE` `MARKET` `GLOBAL` `CUSTOM`

### 다른 캘린더에서 구독
사이트의 **캘린더 구독용 .ics** 버튼으로 현재 필터가 적용된 일정을 내려받아
구글/애플 캘린더에 가져올 수 있습니다.

---

## 로컬 개발

```bash
pip install -r requirements.txt
python -m collectors.run --only manual rules   # 네트워크 없이 도는 소스
python -m http.server -d docs 8000             # http://localhost:8000
```

---

## 현재 상태

| 소스 | ID | 상태 |
|---|---|---|
| 직접 입력 | `manual` | 동작 |
| 정기 공표 추정 | `rules` | 동작 (전부 잠정) |
| 한국은행 주요일정 | `bok` | **미검증** — 셀렉터 확인 필요 |
| 국회 의사일정 | `assembly` | **미검증** — 서비스 ID·필드명 확인 필요 |
| 공휴일 | `holiday` | **미검증** — 키 발급 후 확인 필요 |

미검증 어댑터는 `optional=True` 라 실패해도 전체 수집을 막지 않습니다.
실제 응답으로 확인한 뒤 `optional=False` 로 바꾸세요.

---

## 데이터에 대한 주의

수집한 일정은 참고용입니다. 특히 부동산 대책처럼 사전 예고 없이 발표되는 사안은
일정 자체가 유동적입니다. `잠정` 배지가 붙은 항목은 공표 주기로 계산한 추정치이며
실제와 다를 수 있습니다. 판단이 필요한 일에는 반드시 원문 링크로 확인하세요.

수집은 공식 OpenAPI 를 우선하고, HTML 을 읽을 때도 robots.txt 를 확인한 뒤
요청 간격을 두고 하루 두 번만 접근합니다.
