# biz-health-check

> 사업자등록번호와 상호를 바탕으로 6개 공공 출처를 교차 조회하고, 판단 점수 없이 확인된 사실만 한 장에 모으는 사업자 실사 스킬입니다.

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

## 해결하는 문제

거래처 확인은 사업자 상태 하나만 봐서는 부족합니다. 계속사업자인지, 공개 자료상 직원 규모가 있는지, 고액·상습체납 명단이나 현재 유효한 조달 제재가 있는지, 법인 개요와 인허가 상태가 서로 맞는지 별도 출처를 오가야 합니다. 이 스킬은 하위 조회 도구의 원문 결과를 한 리포트에 병렬 배치합니다.

## 조회 범위

| 섹션 | 확인 내용 | 하위 스킬 |
|---|---|---|
| 국세청 상태 | 계속·휴업·폐업, 과세유형 | `nts-business-registration` |
| 국민연금 | 가입자수, 고지금액, 취득·상실 추이 | `national-pension-workplace` |
| 체납 명단 | 공개된 고액·상습체납 후보 | `nts-tax-delinquency` |
| 금융위원회 | 대표자, 설립일, 업종 등 법인 개요 | `fsc-corporate-info` |
| 나라장터 | 조회시점 현재 유효한 부정당제재 | `g2b-sanctioned-supplier` |
| LOCALDATA | 인허가 업종의 영업·휴업·폐업 상태 | `localdata-business-status` |

## 이런 요청에 사용합니다

- “이 거래처가 실제 영업 중인지 한 번에 확인해줘.”
- “직원 규모와 공개 체납·입찰 제재를 같이 봐줘.”
- “사업자번호와 상호가 여러 공개자료에서 같은 회사로 보이는지 대조해줘.”

## 입력과 결과물

필수 또는 선택 입력:

- 사업자등록번호 10자리: 국세청 상태와 조달 제재 조회
- 상호·법인명: 국민연금, 금융위, 체납, 인허가 조회
- 시군구와 업종: LOCALDATA 조회 정밀화

결과는 각 섹션의 원문 데이터, 출처, 조회시각, 일치 근거 또는 `unavailable` 사유를 담습니다. 일부 조회가 실패해도 전체 리포트를 중단하지 않습니다.

## 빠른 시작

```bash
python install.py --no-law-mcp --skills biz-health-check,nts-business-registration,national-pension-workplace,nts-tax-delinquency,fsc-corporate-info,g2b-sanctioned-supplier,localdata-business-status
```

저장소에서 직접 실행:

```bash
python skills/biz-health-check/scripts/biz_health_check.py 124-81-00998 --name "삼성전자"
python skills/biz-health-check/scripts/biz_health_check.py --name "호텔샬롬" --region 제주제주시 --industry 숙박업
```

## 의존성과 데이터 경계

- Python과 인터넷 연결이 필요합니다.
- 국세청·국민연금·금융위·조달청 섹션은 `k-skill-proxy`가 필요합니다.
- 체납 명단과 LOCALDATA는 사용자 머신에서 공개 사이트를 직접 조회합니다.
- 사업자번호가 공개되지 않는 출처에서는 상호 문자열 후보만 제시하며 동일성을 단정하지 않습니다.

## 포함 파일

```text
biz-health-check/
├─ SKILL.md
├─ README.md
└─ scripts/biz_health_check.py
```

## 한계와 안전 경계

- 신용점수, 위험등급, 거래 승인·거절 결론을 만들지 않습니다.
- “검색 결과 없음”을 “문제가 전혀 없음”으로 해석하지 않습니다.
- 공개 범위와 갱신 주기가 다른 자료를 같은 시점의 완전한 기업 상태로 오인하지 않습니다.
