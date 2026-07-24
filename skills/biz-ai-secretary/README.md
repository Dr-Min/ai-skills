# biz-ai-secretary 🎯

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
