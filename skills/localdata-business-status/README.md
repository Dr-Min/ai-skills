# localdata-business-status

> LOCALDATA 지역별 인허가 파일에서 식당·카페·숙박·약국·미용실·학원 등 208개 업종의 영업 상태와 업력을 확인합니다.

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

## 해결하는 문제

사업자등록번호를 모르는 동네 사업장도 상호와 시군구로 영업·휴업·폐업 상태, 인허가일, 폐업일, 업태와 주소를 확인할 수 있습니다. 인증키 없이 행정안전부 공개 파일을 직접 내려받아 검색합니다.

## 이런 요청에 사용합니다

- “제주시의 이 호텔이 현재 영업 중인지 봐줘.”
- “이 식당은 언제 인허가를 받았어?”
- “같은 상호의 약국 후보와 주소를 찾아줘.”

## 입력과 결과물

- `--name`: 상호 또는 사업장명
- `--region`: `제주제주시`, `서울종로구`, `경기수원시` 같은 시군구
- `--industry`: 업종명 또는 slug, 여러 번 지정 가능

결과에는 영업상태, 상세상태, 인허가일, 폐업일, 업태, 도로명·지번주소, 데이터 갱신시점이 포함됩니다. 동일 상호가 여러 개면 모든 후보를 보여줍니다.

## 설치와 실행

```bash
python install.py --no-law-mcp --skills localdata-business-status

python skills/localdata-business-status/scripts/localdata_business_status.py \
  --name "호텔샬롬" --region 제주제주시 --industry 숙박업
```

추가 Python 패키지는 필요하지 않습니다. 큰 전국 통파일 대신 지역 파일을 사용하며 내려받은 파일은 하루 동안 로컬 캐시합니다.

## 포함 파일

```text
localdata-business-status/
├─ SKILL.md
├─ README.md
├─ data/
│  ├─ localdata_industries.json
│  └─ localdata_orgcodes.json
└─ scripts/localdata_business_status.py
```

## 데이터 한계와 개인정보

- LOCALDATA에는 사업자등록번호가 없으므로 상호와 주소 후보만 대조합니다.
- 입력한 상호와 지역은 공개 파일 다운로드 요청에 사용됩니다.
- 자료는 약 2일 전 기준으로 현행화될 수 있어 오늘의 실제 영업상태와 차이가 날 수 있습니다.
- 결과 없음은 인허가 부재, 표기 차이, 업종 선택 오류 중 하나일 수 있습니다.

공식 사이트: [지방행정 인허가데이터](https://www.localdata.go.kr)
