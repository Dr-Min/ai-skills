# 스킬 구조 자세히 (anatomy)

## 폴더와 파일

스킬은 **폴더 하나**입니다. 폴더 이름이 곧 스킬 이름이고, 영어 소문자와 하이픈만 씁니다
(`my-skill`, `contract-review`, `weekly-report`). 그 안에 최소한 `SKILL.md`가 있어야 합니다.

```
contract-review/
├── SKILL.md            (필수) — 지침 본체 + frontmatter
├── references/         (선택) — 길어지는 내용을 뺀 참고 문서
│   ├── clauses.md
│   └── checklist.md
├── scripts/            (선택) — 반복 작업을 자동화하는 실행 코드(파이썬 등)
└── assets/             (선택) — 결과물에 쓰는 템플릿·아이콘·폰트
```

- `references/` — Claude가 **필요할 때만 읽는** 문서. 여기에 상세 규칙·예시를 둡니다.
- `scripts/` — 매번 똑같이 돌리는 계산·변환을 코드로 박아둠(예: `make_report.py`). 스킬이
  이 스크립트를 "실행하라"고 시키면, 매번 새로 짜는 낭비가 없어집니다.
- `assets/` — 문서 템플릿, 로고 등 **결과물에 들어가는 파일**.

## Frontmatter (맨 위 설정 블록)

`SKILL.md` 맨 위, `---` 두 줄 사이에 씁니다. 여기 두 개가 **필수**:

```yaml
---
name: contract-review
description: 계약서를 검토하는 스킬. "계약서 봐줘", "독소조항 찾아줘" 등에서 켜진다.
---
```

- **name** — 스킬 식별자. 폴더 이름과 똑같이(소문자-하이픈).
- **description** — **가장 중요.** "무엇을 하고 + 언제 켜지는지." Claude가 스킬을 켤지 말지
  오직 이 문장을 보고 판단합니다. (쓰는 법은 `writing-guide.md`)

## Progressive disclosure (점진적 공개) — 왜 파일을 나누나

Claude는 스킬을 **3단계로 나눠 읽습니다.** 이걸 알면 왜 파일을 쪼개는지 이해됩니다:

1. **1단계 — name + description만** 항상 켜져 있음(약 100단어). 여기서 "이 스킬 쓸까?"를 판단.
2. **2단계 — SKILL.md 본문** 스킬이 켜지면 읽음(가급적 500줄 이내).
3. **3단계 — references/의 파일들** 본문이 "이건 저 파일 봐"라고 가리킬 때만 읽음(분량 무제한).

즉 자주 안 쓰는 상세 내용을 `references/`로 빼두면, 평소엔 안 읽어서 빠르고, 필요할 때만 열어
정확합니다. **본문에는 "언제 어느 파일을 읽어라"는 이정표**를 꼭 남기세요:

```markdown
| 사용자가 ...하면 | 읽을 파일 |
| --- | --- |
| 독소조항을 찾고 싶어 하면 | references/clauses.md |
| 최종 체크리스트가 필요하면 | references/checklist.md |
```

## 규칙 하나: 500줄 넘으면 쪼갠다

`SKILL.md`가 500줄에 가까워지면, 한 단계 계층을 더 만들어 `references/`로 내리고 본문엔
포인터만 남깁니다. 참고파일이 300줄 넘게 길면 그 파일 맨 위에 **목차**를 붙이세요.

## 여러 분야를 다룰 땐 분야별로 나눈다

한 스킬이 여러 갈래(예: AWS/GCP/Azure)를 다루면, 본문에서 "무엇을 고를지"만 정하고 갈래별
상세는 각각의 참고파일로:

```
cloud-deploy/
├── SKILL.md            (공통 흐름 + 선택 안내)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```
