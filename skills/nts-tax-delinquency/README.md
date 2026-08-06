# nts-tax-delinquency

> 국세청 누리집의 고액·상습체납자 공개 명단에서 법인명과 상호가 일치하는 공개 후보를 검색합니다.

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

## 확인하는 내용

- 법인 명단: 공개년도, 법인명, 대표자, 업종, 소재지, 총 체납액, 세목, 체납건수와 요지
- 개인 명단: 공개년도, 성명, 연령, 상호, 직업, 주소, 총 체납액, 세목과 체납요지

## 이런 요청에 사용합니다

- “이 거래처가 국세청 고액·상습체납자 공개 명단에 있는지 봐줘.”
- “법인명뿐 아니라 같은 상호로 공개된 개인 후보도 대조해줘.”

## 설치와 실행

```bash
python install.py --no-law-mcp --skills nts-tax-delinquency
python skills/nts-tax-delinquency/scripts/nts_tax_delinquency.py --name "○○건설"
```

Python 표준 라이브러리만 사용하며 별도 인증키가 필요 없습니다. 국세청 공개 검색을 사용자 머신에서 읽기 전용으로 호출합니다.

## 결과 해석

명단에는 사업자등록번호가 없으므로 상호·법인명 문자열이 일치하는 후보만 나열합니다. 동명이인이나 동명 법인의 동일성을 자동 확정하지 않습니다. 0건은 공개 명단에서 문자열 매치를 찾지 못했다는 의미일 뿐, 일반적인 체납이 전혀 없다는 증명이 아닙니다.

## 실패 처리

- 입력 누락, 네트워크 오류, 페이지 구조 변경은 `unavailable`로 반환
- HTML 구조가 예상과 다르면 추측 파싱하지 않고 수동 확인 URL 안내
- 결과가 없더라도 조회시점과 검색어를 기록

## 포함 파일

```text
nts-tax-delinquency/
├─ SKILL.md
├─ README.md
└─ scripts/nts_tax_delinquency.py
```

## 안전 경계

공개된 사실과 출처만 제시하며 위험점수, 신용판정, 거래 거절 결론을 생성하지 않습니다. 공식 검색: [국세청 명단공개](https://www.nts.go.kr/nts/ad/openInfo/selectList.do)
