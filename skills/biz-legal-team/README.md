# biz-legal-team ⚖️

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

> 1인사업자·소상공인이 변호사 만나기 직전까지 자료를 정리해 주는 법무 보조자.
> 5개 모드: 생성·점검·독소·용어·상담준비.

설치: `python install.py --skills biz-legal-team`

---

## 🚀 빠른 시작

### 슬래시 호출

```
/biz-legal-team 점검 ~/Documents/외주계약서.pdf
/biz-legal-team 독소 ~/Downloads/거래처A_계약서.hwp
/biz-legal-team 생성 외주
/biz-legal-team 용어 연대보증
/biz-legal-team 상담준비 [고민 한 줄]
```

### 자동 트리거 (자연어)

- "이 계약서 점검해줘" → 점검 모드
- "위약금 30% 너무 과해?" → 독소 모드
- "변호사 만나기 전 준비" → 상담준비 모드
- "갑·을 차이가 뭐야?" → 용어 모드

---

## 📦 폴더 구조

```
biz-legal-team/
├── SKILL.md                              # 시스템 프롬프트 + 모드 정의
├── README.md                             # 본 파일
├── checklists/                           # 점검 카탈로그
│   ├── 7-essential-clauses.md                   #   - 원고 Slide 19
│   ├── 5-missing-clauses.md                     #   - 원고 Slide 20
│   ├── 5-payment-safeguards.md                   #   - 원고 Slide 22
│   └── 12-toxic-clauses.md                      #   - 자체 카탈로그 ⭐
├── templates/                            # 생성·상담준비 모드용
│   ├── outsourcing-contract.md
│   ├── service-contract.md
│   ├── nda-template.md
│   └── lawyer-consultation-4pack.md
└── samples/                              # 학습용 샘플
    ├── toxic-case-1-unilateral-termination.md
    ├── toxic-case-2-excessive-penalty.md
    └── toxic-case-3-unlimited-liability.md
```

---

## 🧩 5개 모드 요약

| #   | 모드        | 트리거            | 산출물                            |
| --- | ----------- | ----------------- | --------------------------------- |
| 1   | 생성        | `생성 [거래종류]` | 표준계약서 기반 초안              |
| 2   | 점검        | `점검 [파일경로]` | 7대 + 5빠진 + 미수금 5장치 점검표 |
| 3   | **독소** ⭐ | `독소 [파일경로]` | 12종 검출 + 변경 제안 + 협상 톤   |
| 4   | 용어        | `용어 [단어]`     | 한 줄 풀이 + 함정 + 등장 패턴     |
| 5   | 상담준비    | `상담준비 [고민]` | 변호사 4점 패키지                 |

---

## 🔗 Korean Law MCP 연동

본 스킬은 `korean-law` MCP 도구를 활용해 법령·판례를 실시간 인용합니다.

| 모드     | 1차 도구                                  | 인용 법령                          |
| -------- | ----------------------------------------- | ---------------------------------- |
| 점검     | `legal_research(task="document_review")` | 민법, 약관규제법                   |
| 독소     | `legal_research` + `search_decisions`    | 약관규제법 제6·8·9조, 민법 제398조 |
| 상담준비 | `legal_research(task="dispute_prep")`    | 사안별 판례                        |

`/my-lawyer` 스킬과 도구는 공유, 호출 방식만 다름.

---

## 🛡️ 안전 가드레일

1. **면책 고지 자동 출력** — 모든 답변 시작에 ⚖️
2. **단정 표현 자동 감지** — "~합니다" → "~할 수 있습니다 / 변호사 확인"
3. **빨강 영역 7가지** — 답변 끝에 "변호사 확인 필요" 자동 푸터
4. **법령 인용 시 조회일자** — 기억 답변 금지

---

## 📚 관련 스킬

- **`/my-lawyer`** — 법령·판례 단독 조회 (형제 스킬)
- **`/legal-lead-kr`** — 한국 스타트업 법무팀장 (스타트업 타겟)
- **`/세무조정계산서분석`** — 법인세 신고서 분석

---

## 🆘 트러블슈팅

### 슬래시 호출 시 다른 스킬이 떠요

- SKILL.md 프론트매터 `user_invocable: true` 확인
- Claude Desktop 재시작

### 답변에 면책 고지 ⚖️가 안 나와요

- SKILL.md "필수 면책 고지" 섹션 확인
- AI에게 명시: "답변 시작에 ⚖️ 면책 고지 추가해 주세요"

### 법령 인용에 조회일자가 없어요

- Codex에서 `korean-law` MCP 도구가 활성화되어 있는지 확인
- 미설정 시 일반 지식 답변 + "법령 본문 미확인" 경고 표시

### 독소조항 검출 결과가 부족해요

- 12종 카탈로그(`checklists/12-toxic-clauses.md`) 모두 검토했는지 확인
- AI에게 명시: "12종 매트릭스 표 형식으로 모두 출력"

---

## 🔄 업데이트 이력

- **v1.0 (2026-05-06)**: 초기 빌드. 5개 모드 + 4 checklists + 4 templates + 3 samples.

---

🛡️ **본 스킬은 변호사 만나기 전 준비 도구입니다.**
**서명·소송·중대 결정은 변호사 검토 후 본인이.**
