# biz-ai-secretary 🎯

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

> 1인사업자·소상공인의 통합 AI 비서 디스패처.
> 3개 팀장(법무·세무·재무)을 한 번에 호출 + 통합 진단 + 7일 실행계획.

---

## 🚀 빠른 시작

```
/biz-ai-secretary 통합          # 한 장 진단
/biz-ai-secretary [자연어 질문]   # 자동 라우팅
/biz-ai-secretary 7일계획        # 1개 작업 카드
/biz-ai-secretary 상태           # 프로필 + 이력
```

자연어 자동 분기:

- "위약금 30% 과해?" → /biz-legal-team 독소
- "노란우산 절세 효과?" → /biz-tax-team 절세
- "정책자금 가능?" → /biz-finance-team 자가진단

## 📦 폴더 구조

```
biz-ai-secretary/
├── SKILL.md                              # 디스패처 + 4개 모드
├── README.md
└── templates/
    ├── unified-master-1page.md                # 한 장 진단
    ├── 7-day-execution-card.md                    # 1개 작업 카드
    └── routing-keywords-dict.md             # 자연어 분기 사전
```

## 🧩 4개 모드

| 모드        | 트리거    | 동작                    |
| ----------- | --------- | ----------------------- |
| **통합** ⭐ | `통합`    | 3팀장 병렬 → 마스터 1장 |
| 라우팅      | 자연어    | 자동 분기               |
| 7일계획     | `7일계획` | 1개 작업 카드           |
| 상태        | `상태`    | 프로필 + 이력           |

## 🛡️ 안전 가드

- 7일 계획에 1개 이상 작업 권장 금지
- 팀장 스킬 우회 직접 답변 금지
- 모든 답변 끝에 빨강 7영역 푸터

## 📚 종속 스킬

- /biz-legal-team (병렬 호출)
- /biz-tax-team (병렬 호출)
- /biz-finance-team (병렬 호출)
- /biz-profile (프로필 없을 때 자동)
- /biz-monthly-sop (월간 매뉴얼)
- /biz-color-map (업무 분류)

🛡️ **모든 결정은 전문가 + 본인이.** AI는 통합 정리까지만.

## 해결하는 문제

사업 고민은 법무·세무·재무가 동시에 얽히는 경우가 많지만 사용자는 어떤 팀 스킬부터 불러야 할지 판단하기 어렵습니다. 이 스킬은 자연어 질문을 적합한 팀으로 보내거나 세 팀의 진단을 하나의 우선순위 문서로 합칩니다.

## 입력과 결과물

- 입력: 사업 프로필, 현재 고민, 계약·증빙·자금 관련 자료
- 통합 결과: 법무 5개, 세무 5개, 재무 5개 핵심 항목과 전문가 질문
- 실행 결과: 이번 주에 실제로 끝낼 한 개의 작업과 완료 기준
- 상태 결과: 현재 사업 프로필, 누락 정보와 최근 작업 이력

## 설치

```bash
python install.py --skills biz-profile,biz-ai-secretary,biz-legal-team,biz-tax-team,biz-finance-team,biz-monthly-sop,biz-color-map
```

법령 MCP 없이 재무·프로필·색상 분류만 사용할 수도 있지만, 법무·세무 통합 진단에는 Korean Law MCP 연결을 권장합니다.

## 한계

팀별 결과를 정리하고 충돌을 드러내는 역할입니다. 계약 체결, 세금 신고, 대출 신청 같은 외부 상태 변경을 대신 확정하지 않으며, 빨강 영역은 반드시 사용자와 전문가에게 돌려보냅니다.
