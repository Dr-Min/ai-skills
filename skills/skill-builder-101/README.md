# skill-builder-101

> 반복 업무를 재사용 가능한 Codex 스킬로 바꾸는 과정을 한국어로 설명하고, 첫 `SKILL.md`부터 설치·배포까지 함께 만드는 초보자용 가이드입니다.

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

## 스킬이란?

스킬은 모델을 다시 훈련하는 기능이 아니라 특정 상황에서 AI가 펼쳐 읽는 지침과 도구 묶음입니다. 잘 만든 스킬은 같은 종류의 요청을 받을 때마다 같은 기준, 순서와 안전 경계를 재사용하게 합니다.

## 이런 요청에 사용합니다

- “나만의 Codex 스킬을 만들고 싶어.”
- “매번 반복하는 이 업무를 자동화 규칙으로 저장해줘.”
- “`SKILL.md`와 description을 어떻게 써야 해?”
- “스킬에 MCP나 외부 도구를 연결하고 싶어.”
- “설치 가능한 패키지나 플러그인으로 배포하고 싶어.”

## 만드는 다섯 단계

1. **의도 잡기** — 무엇을 하고, 어떤 말에 실행되며, 결과물이 무엇인지 정합니다.
2. **구조 설계** — 짧으면 `SKILL.md`, 세부 지식은 `references/`, 반복 코드는 `scripts/`, 출력 재료는 `assets/`로 나눕니다.
3. **트리거와 본문 작성** — description에는 무엇과 언제, 본문에는 실제 실행 절차와 이유를 씁니다.
4. **도구 연결** — 필요한 경우 MCP, 앱, CLI와 자격증명 경계를 설계합니다.
5. **검증과 배포** — 구조 검사, 실제 예시 테스트, 설치와 저장소·플러그인 배포를 진행합니다.

## 가장 자주 생기는 실패

- description이 추상적이라 필요한 순간에 스킬이 실행되지 않음
- 모든 내용을 한 파일에 넣어 컨텍스트를 과도하게 소비함
- “무엇을 하라”만 있고 실패 조건과 이유가 없음
- 비밀값, 사용자 전용 파일, 불필요한 산출물을 패키지에 포함함
- 예시 실행 없이 파일 구조만 만들어 완료했다고 판단함

## 입력과 결과물

입력은 만들고 싶은 업무, 실제 사용 문장, 기대 결과물, 필요한 외부 도구와 위험 경계입니다. 결과는 다음을 포함할 수 있습니다.

- 이름과 트리거가 포함된 `SKILL.md`
- 필요한 `references/`, `scripts/`, `assets/`
- UI 표시용 `agents/openai.yaml`
- 구조 검증과 현실적인 테스트 결과
- 설치·패키징·배포 방법

## 설치와 사용 예시

```bash
python install.py --no-law-mcp --skills skill-builder-101
```

```text
$skill-builder-101 매주 들어오는 제안요청서를 읽고 필수 제출항목을 체크하는 스킬을 만들어줘.
```

## 참고 모듈

| 파일 | 내용 |
|---|---|
| `references/anatomy.md` | 스킬 폴더와 파일 역할 |
| `references/writing-guide.md` | description과 본문 작성법 |
| `references/examples.md` | 완성된 예시 |
| `references/mcp-integration.md` | MCP 도구 연결과 자격증명 경계 |
| `references/packaging.md` | 설치, `.skill`, Git과 배포 |

## 포함 파일

```text
skill-builder-101/
├─ SKILL.md
├─ README.md
└─ references/
   ├─ anatomy.md
   ├─ examples.md
   ├─ mcp-integration.md
   ├─ packaging.md
   └─ writing-guide.md
```

## 범위

이 스킬은 처음 만드는 사람이 개념을 이해하고 첫 스킬을 완성하도록 돕습니다. 고급 평가 설계, 대규모 벤치마크, UI 메타데이터 자동 생성 같은 작업에는 공식 `skill-creator` 지침을 함께 사용합니다.
