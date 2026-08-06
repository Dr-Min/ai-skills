# g2b-sanctioned-supplier

> 나라장터에서 사업자등록번호와 정확히 일치하는 조회시점 현재 유효 부정당제재를 확인합니다.

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

## 언제 사용하나요?

- 조달 거래나 계약 전 현재 입찰참가자격 제한 여부를 확인할 때
- 제재 시작·종료일, 제재기관, 근거 법률을 공식 데이터로 확인할 때
- `biz-health-check`의 조달 제재 섹션을 실행할 때

## 제공하는 정보

공공데이터포털의 조달청 나라장터 사용자정보 서비스 `getUnptRsttCorpInfo02`를 사용합니다. 사업자등록번호 정확 일치로 제재 기간, 제재기관명, 계약법 구분, 제재근거법률 등 upstream 필드를 반환합니다.

## 중요한 조회 범위

이 API는 **현재 유효한 제재**만 제공합니다. 이미 만료·해제된 제재, 나라장터 미등록업체 또는 개인의 제재 이력은 제공하지 않습니다. 따라서 결과 0건을 “과거 제재도 전혀 없음”으로 해석하면 안 됩니다.

## 설치와 실행

```bash
python install.py --no-law-mcp --skills g2b-sanctioned-supplier
python skills/g2b-sanctioned-supplier/scripts/g2b_sanctioned_supplier.py --bizno 124-81-00998
```

사업자번호는 하이픈을 포함해도 되며 숫자 10자리로 정규화됩니다.

## 의존성과 실패 처리

- Python, 인터넷 연결, `k-skill-proxy` 접근이 필요합니다.
- `DATA_GO_KR_API_KEY`는 프록시 운영 서버에만 둡니다.
- `503`은 서버 키 미설정, `502`는 서비스 활용신청·권한 문제일 가능성이 큽니다.
- 과거 이력이 필요하면 [나라장터](https://www.g2b.go.kr)에서 수동 확인합니다.

## 포함 파일

```text
g2b-sanctioned-supplier/
├─ SKILL.md
├─ README.md
└─ scripts/g2b_sanctioned_supplier.py
```

## 안전 경계

조회 사실과 적용 범위만 제공하며 업체의 신용도, 위험점수, 계약 적격 여부를 자동 판정하지 않습니다.
