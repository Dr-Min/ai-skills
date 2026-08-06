# nts-business-registration

> 국세청 공식 API로 사업자등록 상태를 조회하거나 사업자번호·개업일·대표자명의 진위를 확인합니다.

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

## 두 가지 모드

### 상태조회

사업자등록번호만으로 계속사업자, 휴업자, 폐업자와 과세유형 등 upstream 상태를 확인합니다. 한 요청에 최대 100개까지 처리할 수 있습니다.

### 진위확인

사업자등록번호, 개업일자, 대표자명을 제출해 등록정보 일치 여부를 확인합니다. 상호, 법인등록번호, 업태, 종목, 주소는 선택 입력입니다.

## 이런 요청에 사용합니다

- 거래처 등록 전에 현재 사업 상태를 확인할 때
- 제출받은 사업자등록 정보가 공식 응답과 일치하는지 검증할 때
- `biz-health-check`의 국세청 상태 섹션을 실행할 때

## 설치와 실행

```bash
python install.py --no-law-mcp --skills nts-business-registration

python skills/nts-business-registration/scripts/nts_business_registration.py status \
  --b-no 123-45-67890

python skills/nts-business-registration/scripts/nts_business_registration.py validate \
  --business-json '{"b_no":"123-45-67890","start_dt":"2020-01-31","p_nm":"홍길동"}'
```

## 입력 규칙

- 사업자번호: 숫자 10자리, 하이픈 허용
- 개업일: `YYYYMMDD`, 하이픈·점 허용
- 대표자명: 필수, 최대 30자
- 법인등록번호: 제공 시 숫자 13자리

## 개인정보와 자격증명

진위확인 입력은 hosted proxy와 공공데이터포털 upstream으로 전송됩니다. 필요한 필드만 보내고, 민감한 거래처 데이터가 우려되면 `KSKILL_PROXY_BASE_URL`로 self-host proxy를 사용합니다. `DATA_GO_KR_API_KEY`는 저장소나 사용자 명령에 넣지 않고 프록시 서버에서 관리합니다.

## 결과와 오류

- 상태조회: `b_stt`, `b_stt_cd`, `tax_type` 등 공식 필드
- 진위확인: `valid`, `valid_msg`
- `400`: 형식 오류 또는 필수 입력 누락
- `503`: 프록시 서버 키 미설정
- 인증·승인 오류: 해당 공공데이터 서비스 활용신청 상태 확인 필요

## 포함 파일

```text
nts-business-registration/
├─ SKILL.md
├─ README.md
└─ scripts/nts_business_registration.py
```

공식 문서: [공공데이터포털 15081808](https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15081808)
