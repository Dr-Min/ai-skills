# AI Skills

필요한 것만 골라 설치하는 개인 Codex 스킬 허브입니다. 비즈니스 실무, 공공데이터 조회, 한국 법령, 영상 제작, 교육, 스킬 제작 도구를 하나의 모노레포에서 관리합니다.

## 빠른 시작

```bash
git clone https://github.com/Dr-Min/ai-skills.git
cd ai-skills
python install.py --list
```

Korean Law MCP 없이 원하는 스킬만 설치:

```bash
python install.py \
  --no-law-mcp \
  --skills adaptive-mastery-tutor,cinematic-video-pipeline
```

모든 스킬과 Korean Law MCP 설치:

```bash
python install.py
```

설치기는 법제처 Open API `OC` 값을 요청합니다. 인증값은 Git 저장소가 아닌 사용자 컴퓨터의 `~/.codex/ai-skills/credentials.json`에만 저장됩니다.

## 어떤 스킬을 고르면 되나요?

| 목적 | 추천 스킬 |
|---|---|
| 사업 전체를 한 번에 점검 | [`biz-ai-secretary`](skills/biz-ai-secretary/README.md) |
| 계약서 작성·검토 | [`biz-legal-team`](skills/biz-legal-team/README.md) |
| 영수증·지출·세무 준비 | [`biz-tax-team`](skills/biz-tax-team/README.md) |
| 정책자금·사업계획·현금흐름 | [`biz-finance-team`](skills/biz-finance-team/README.md) |
| 거래처·사업자 실사 | [`biz-health-check`](skills/biz-health-check/README.md) |
| 한국 법령 MCP 연결 | [`law-mcp-setup`](skills/law-mcp-setup/README.md) |
| 단계별 개인 튜터 | [`adaptive-mastery-tutor`](skills/adaptive-mastery-tutor/README.md) |
| 영화형 영상 제작 파이프라인 | [`cinematic-video-pipeline`](skills/cinematic-video-pipeline/README.md) |
| Seedance 2.0 프롬프트 | [`min-edit-seedance-2-0`](skills/min-edit-seedance-2-0/README.md) |
| 음악에 맞춘 컷 편집 | [`sync-cuts-to-music`](skills/sync-cuts-to-music/README.md) |
| 초 단위 시네마틱 스토리보드 | [`timed-storyboard`](skills/timed-storyboard/README.md) |
| 새로운 Codex 스킬 제작 | [`skill-builder-101`](skills/skill-builder-101/README.md) |

각 스킬 이름을 누르면 독립 저장소 수준의 README가 열립니다. 전체를 한 화면에서 비교하려면 [`docs/skill-catalog-ko.md`](docs/skill-catalog-ko.md), 기계가 읽는 이름·경로·문서·의존성은 [`catalog.json`](catalog.json)을 사용하세요.

## 카테고리

### Business

- [`biz-ai-secretary`](skills/biz-ai-secretary/README.md): 법무·세무·재무 통합 디스패처
- [`biz-color-map`](skills/biz-color-map/README.md): 업무를 자동·검토·전문가 영역으로 분류
- [`biz-finance-team`](skills/biz-finance-team/README.md): 정책자금, 사업계획, 월간 재무 점검
- [`biz-health-check`](skills/biz-health-check/README.md): 사업자 공공데이터 교차 조회
- [`biz-legal-team`](skills/biz-legal-team/README.md): 계약서·독소조항·미수금 점검
- [`biz-monthly-sop`](skills/biz-monthly-sop/README.md): 월간 세무·증빙 루틴
- [`biz-profile`](skills/biz-profile/README.md): 사업 프로필 인터뷰와 공통 컨텍스트
- [`biz-tax-team`](skills/biz-tax-team/README.md): 세무 증빙 분류와 세무사 전달 패키지

### Public data

- [`fsc-corporate-info`](skills/fsc-corporate-info/README.md): 금융위원회 법인 기본정보
- [`g2b-sanctioned-supplier`](skills/g2b-sanctioned-supplier/README.md): 나라장터 부정당제재
- [`localdata-business-status`](skills/localdata-business-status/README.md): 지방행정 인허가 영업상태
- [`national-pension-workplace`](skills/national-pension-workplace/README.md): 국민연금 가입 사업장
- [`nts-business-registration`](skills/nts-business-registration/README.md): 사업자등록 상태·진위
- [`nts-tax-delinquency`](skills/nts-tax-delinquency/README.md): 공개 고액·상습체납 명단

### Legal

- [`law-mcp-setup`](skills/law-mcp-setup/README.md): Korean Law MCP 설치·복구·검증

### Media

- [`cinema-studio-pipeline`](skills/cinema-studio-pipeline/README.md): 영화 제작 교육형 파이프라인
- [`cinematic-video-pipeline`](skills/cinematic-video-pipeline/README.md): 재현 가능한 영상 생성 파이프라인
- [`min-edit-seedance-2-0`](skills/min-edit-seedance-2-0/README.md): Seedance 2.0 멀티모달 프롬프트
- [`sync-cuts-to-music`](skills/sync-cuts-to-music/README.md): 트랜지언트 기반 음악 컷 분석과 편집 패키지
- [`timed-storyboard`](skills/timed-storyboard/README.md): 초 단위 쇼트·동선·카메라 스토리보드

### Education and tooling

- [`adaptive-mastery-tutor`](skills/adaptive-mastery-tutor/README.md): 적응형 숙달 학습 튜터
- [`skill-builder-101`](skills/skill-builder-101/README.md): 스킬 구조·작성·패키징 가이드

## 설치 명령

설치 가능한 스킬 확인:

```bash
python install.py --list
```

한 개만 설치:

```bash
python install.py --no-law-mcp --skills skill-builder-101
```

여러 개 설치:

```bash
python install.py \
  --no-law-mcp \
  --skills biz-profile,biz-ai-secretary,biz-tax-team
```

선택 스킬과 Korean Law MCP를 함께 설치:

```bash
python install.py \
  --skills law-mcp-setup,biz-legal-team,biz-tax-team
```

MCP만 설정:

```bash
python install.py --no-skills
```

기존에 같은 이름의 스킬이 있으면 설치 전에 `~/.codex/backups/` 아래로 백업합니다.

## 저장소 구조

```text
ai-skills/
├─ .codex-plugin/plugin.json
├─ .mcp.json
├─ catalog.json
├─ install.py
├─ skills/
│  ├─ biz-ai-secretary/
│  ├─ adaptive-mastery-tutor/
│  ├─ cinematic-video-pipeline/
│  └─ .../
├─ artifacts/
├─ docs/
├─ scripts/
└─ tests/
```

각 설치 단위는 `skills/` 바로 아래에서 자체 `SKILL.md`를 가진 독립 폴더입니다. 플러그인 호환성을 위해 폴더는 평탄하게 유지하고 분야 분류는 `catalog.json`에서 관리합니다.

## 요구사항

- Python 3.9 이상
- Codex
- Korean Law MCP 사용 시 Node.js 20.19 이상
- 법령 API 사용 시 국가법령정보센터 Open API `OC`
- 일부 공공데이터 스킬은 별도 프록시 또는 API 연결 필요
- 미디어 생성 스킬은 해당 생성 서비스·MCP 연결 필요

## 보안

- 실제 `.env`, 토큰, 쿠키, 인증값을 커밋하지 않습니다.
- `OC`는 로컬 credentials 파일에 권한을 제한해 저장합니다.
- 설치 전 기존 설정과 동명 스킬을 백업합니다.
- 법률·세무·재무 결과는 공식 자료와 전문가 확인을 대체하지 않습니다.
- 공개 데이터 조회 결과는 사실을 나열하며 임의의 신용점수나 위험등급을 만들지 않습니다.

자세한 내용은 [`SECURITY.md`](SECURITY.md)를 참고하세요.

## 라이선스

이 저장소는 공개되어 있지만 저장소 전체에 적용되는 단일 오픈소스 라이선스는 아직 없습니다. 개별 `SKILL.md`에 라이선스가 명시된 항목만 해당 조건으로 재사용할 수 있으며, 나머지 자료는 별도 허가 없이 복제·재배포할 수 있는 것으로 간주하지 마세요. 자세한 내용은 [`NOTICE.md`](NOTICE.md)를 참고하세요.

## 개발과 검증

```bash
python -m unittest discover -s tests -v
python scripts/validate_package.py
python install.py --list
```

플러그인 manifest는 `.codex-plugin/plugin.json`, MCP 연결은 `.mcp.json`에서 관리합니다.

## 통합 출처

다음 기존 저장소의 Git 이력을 보존해 통합했습니다.

- `Dr-Min/biz-law-codex`
- `Dr-Min/higgs-skills`
- `Dr-Min/cinematic-video-pipeline`
- `Dr-Min/adaptive-mastery-tutor`
- `Dr-Min/min-edit-seedance-2-0`

기존 저장소는 통합 검증이 끝날 때까지 삭제하지 않습니다.
