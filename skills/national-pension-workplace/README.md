# national-pension-workplace

> 국민연금 가입 사업장 공개자료로 사업장 후보, 가입자 수, 당월 고지금액, 취득·상실 인원과 월별 변화를 조회합니다.

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

## 이런 요청에 사용합니다

- “이 회사의 공개된 직원 규모를 국민연금 가입자수로 봐줘.”
- “최근 가입 인원이 늘었는지 줄었는지 확인해줘.”
- “사업장명과 사업자번호 앞자리로 후보를 좁혀줘.”

## 작동 방식

공공데이터포털의 국민연금 가입 사업장 내역 V2를 `k-skill-proxy` 경유로 조회합니다. 공개 데이터의 사업자번호는 앞 6자리만 제공되므로 사업장명이 필수입니다. 후보가 여러 개면 임의 선택하지 않고 목록으로 반환합니다.

## 입력과 결과물

- `--name`: 사업장명, 필수
- `--b-no`: 사업자등록번호, 선택. 앞 6자리 필터에만 사용

단일 후보가 특정되면 가입자수, 당월 고지금액, 신규취득·상실 인원과 월별 시계열을 제공합니다.

## 설치와 실행

```bash
python install.py --no-law-mcp --skills national-pension-workplace

python skills/national-pension-workplace/scripts/national_pension_workplace.py \
  --name "삼성전자(주)" --b-no 124-81-00998
```

## 의존성과 오류

- Python, 인터넷 연결, `k-skill-proxy`가 필요합니다.
- 공공데이터 키는 프록시 운영 서버에만 저장합니다.
- `503`은 서버 키 미설정, `502`는 활용신청·권한 문제를 뜻할 수 있습니다.
- `selected_candidate: null`이면 사용자가 후보 목록을 보고 추가 식별해야 합니다.

## 포함 파일

```text
national-pension-workplace/
├─ SKILL.md
├─ README.md
└─ scripts/national_pension_workplace.py
```

## 해석 주의

국민연금 가입자 수는 전체 재직자 수와 동일하지 않을 수 있습니다. 소규모·개인 사업장은 공개 범위에서 빠질 수 있으며, 인원 변화만으로 경영상태를 단정하지 않습니다.
