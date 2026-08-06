# fsc-corporate-info

> 금융위원회 기업기본정보 서비스에서 법인명으로 대표자·설립일·업종 등 법인 개요를 조회합니다.

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

## 언제 사용하나요?

- 법인명으로 기본적인 회사 개요를 확인할 때
- 입력한 사업자번호와 응답 후보의 `bzno`가 일치하는지 대조할 때
- 거래처 실사 리포트에 금융위원회 공식 데이터를 추가할 때

## 작동 방식

공공데이터포털의 `금융위원회_기업기본정보 서비스` 중 `getCorpOutline_V2`를 `k-skill-proxy` 경유로 호출합니다. API 검색키는 법인명 또는 13자리 법인등록번호이며, 사업자등록번호만으로는 검색할 수 없습니다.

응답에 사업자번호가 포함되면 입력값과 정확 일치 후보를 분리합니다. 사업자번호가 없는 응답은 교차검증 불가로 표시합니다.

## 입력과 결과물

- `--name`: 법인명, 필수
- `--b-no`: 사업자등록번호, 선택적 교차검증용

결과에는 upstream 후보 목록, 대표자·설립일·업종 등 제공 필드, 출처와 조회 결과가 포함됩니다.

## 설치와 실행

```bash
python install.py --no-law-mcp --skills fsc-corporate-info
python skills/fsc-corporate-info/scripts/fsc_corporate_info.py --name "삼성전자" --b-no 124-81-00998
```

기본 hosted proxy를 사용하며, self-host 환경에서는 `KSKILL_PROXY_BASE_URL`만 로컬 환경변수로 설정합니다. `DATA_GO_KR_API_KEY`는 사용자 컴퓨터나 저장소가 아니라 프록시 운영 서버에 둡니다.

## 실패를 해석하는 법

- `400`: 법인명 누락
- `503`: 프록시 서버에 공공데이터 키가 없음
- `502`: 해당 서비스 활용신청 또는 권한 문제
- 빈 결과: 법인명 표기를 바꿔 재검색할 필요가 있음

## 포함 파일

```text
fsc-corporate-info/
├─ SKILL.md
├─ README.md
└─ scripts/fsc_corporate_info.py
```

## 데이터 한계

법인등록번호와 사업자등록번호를 혼동하지 않으며, 후보가 여러 개인 경우 임의로 하나를 선택하지 않습니다. 공식 출처: [공공데이터포털 15043184](https://www.data.go.kr/data/15043184/openapi.do).
