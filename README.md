# AI Skills

필요한 것만 골라 설치하는 개인 Codex 스킬 허브입니다. 비즈니스 실무, 공공데이터 조회, 한국 법령, 영상 제작, 교육, 스킬 제작 도구 **22개**를 하나의 모노레포에서 관리합니다.

각 `skills/<name>/` 폴더는 독립적으로 설치할 수 있는 하나의 스킬입니다. 비슷해 보이는 이름도 같은 스킬의 별칭이 아닙니다. 특히 `cinema-studio-pipeline`은 작품 전체의 승인·연속성·계보를 관리하는 제작 운영체계이고, `cinematic-video-pipeline`은 한 클립을 생성·보간·업스케일하는 기술 실행 파이프라인입니다.

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

## 영상 제작 스킬은 어떻게 다른가요?

다섯 스킬은 중복 이름이나 상·하위 버전이 아니라 제작 단계별로 책임이 다릅니다.

| 스킬 | 책임 범위 | 이 스킬을 먼저 고르는 경우 | 대표 결과물 |
|---|---|---|---|
| [`cinema-studio-pipeline`](skills/cinema-studio-pipeline/README.md) | **작품 전체 제작 운영**. Story → Storyboard → Lookdev → Asset lock → Shot still → Raw video → Edit → Finish의 게이트, 사용자 승인, SHA-256 계보, 캐릭터·장소·음성 연속성을 관리 | 여러 쇼트나 캐릭터가 있는 작품을 처음부터 납품까지 통제하고, 무엇을 실제로 승인했는지 증명해야 할 때 | 프로젝트 레코드, 중앙 승인 기록, 자산·테이크 계보, 검증된 타임라인과 납품 기록 |
| [`cinematic-video-pipeline`](skills/cinematic-video-pipeline/README.md) | **한 클립의 기술 실행**. 이미지 생성 → 이미지 투 비디오 → RIFE 60fps → 선택적 ESRGAN 업스케일을 재현 가능한 CLI로 수행 | 프롬프트나 시작 이미지를 실제 고해상도 영상 클립으로 빠르게 만들고 로컬 후처리까지 이어 갈 때 | 단계별 PNG·MP4, 60fps 클립, 선택적 업스케일본 |
| [`timed-storyboard`](skills/timed-storyboard/README.md) | **프리프로덕션 설계**. 이야기를 초·프레임 단위 쇼트, 행동, 시선, 소품, 카메라 동선과 선택적 공간 제어 맵으로 변환 | 생성 전에 “누가 언제 어디로 움직이는가”를 고정하거나 복수 인물의 자리·가림·깊이를 설계할 때 | `storyboard_plan.json`, 쇼트리스트 CSV, 동선 CSV, 러프보드, 공간 제어 패킷 |
| [`min-edit-seedance-2-0`](skills/min-edit-seedance-2-0/README.md) | **Seedance 프롬프트 전문화**. 멀티모달 참조 역할, `@` 참조, 카메라·동작 지시와 Higgsfield 입력을 설계 | Seedance 2.0에 넣을 프롬프트와 이미지·영상·오디오 참조 역할을 정확히 정리할 때 | 생성 프롬프트, 참조 매핑, Higgsfield 제출 입력 |
| [`sync-cuts-to-music`](skills/sync-cuts-to-music/README.md) | **음악 기반 편집**. BPM 격자가 아닌 실제 트랜지언트와 공격음을 분석해 컷 후보와 편집 패키지를 생성 | 이미 있는 이미지·영상 소스를 음악의 필·드럼·전환에 맞춰 편집할 때 | 컷 계획 JSON, 진단 그래프, 분할 클립, 기준 MP4, 선택적 CapCut 초안 |

### 영상 작업 선택 기준

- **작품 전체를 운영한다** → `cinema-studio-pipeline`
- **한 개의 영상 클립을 생성·보간·업스케일한다** → `cinematic-video-pipeline`
- **대본을 쇼트와 동선으로 먼저 설계한다** → `timed-storyboard`
- **Seedance 입력 프롬프트만 정교하게 만든다** → `min-edit-seedance-2-0`
- **완성된 소스를 음악에 맞춰 자른다** → `sync-cuts-to-music`

긴 작품에서는 `cinema-studio-pipeline`을 제작의 중심으로 두고, 필요한 단계에서 나머지 네 스킬을 전문 모듈로 함께 사용할 수 있습니다. 예를 들면 `timed-storyboard`로 동선을 설계하고, `min-edit-seedance-2-0`으로 생성 입력을 작성하고, `cinematic-video-pipeline`으로 클립을 만든 뒤, `sync-cuts-to-music`의 컷 제안을 타임라인 검토에 활용합니다. 이 조합은 권장 예시이며 모든 작품에 네 스킬이 전부 필요한 것은 아닙니다.

## 전체 스킬 카탈로그 — 22개

아래 목록은 설치 가능한 스킬 전체입니다. 각 이름을 누르면 해당 스킬의 상세 README가 열립니다. 더 긴 비교 설명은 [`docs/skill-catalog-ko.md`](docs/skill-catalog-ko.md), 기계가 읽는 이름·경로·의존성의 최종 목록은 [`catalog.json`](catalog.json)을 사용하세요.

### Business — 사업 운영 8개

| 스킬 | 정확한 역할 | 먼저 사용하는 경우 |
|---|---|---|
| [`biz-ai-secretary`](skills/biz-ai-secretary/README.md) | 법무·세무·재무 팀 결과를 한 번에 묶는 통합 디스패처 | 사업 전체의 우선순위와 이번 주 실행 항목이 필요할 때 |
| [`biz-color-map`](skills/biz-color-map/README.md) | 사업 업무를 AI 자동 처리·사람 검토·전문가 전용으로 분류 | 어떤 일을 AI에 맡겨도 되는지 경계를 정할 때 |
| [`biz-finance-team`](skills/biz-finance-team/README.md) | 정책자금, 사업계획서, 현금흐름, 은행 상담 준비 | 자금 신청 가능성과 매월 핵심 숫자를 점검할 때 |
| [`biz-health-check`](skills/biz-health-check/README.md) | 여섯 공공데이터 스킬을 묶어 사업자 사실을 교차 조회 | 신규 거래처나 사업자의 공개 정보를 실사할 때 |
| [`biz-legal-team`](skills/biz-legal-team/README.md) | 계약서 필수·독소조항, 미수금 장치, 수정 문안 점검 | 계약서를 작성하거나 서명 전에 검토할 때 |
| [`biz-monthly-sop`](skills/biz-monthly-sop/README.md) | 결제 직후부터 신고 전까지 월간 세무·증빙 루틴 구성 | 반복 가능한 월간 정리 절차가 필요할 때 |
| [`biz-profile`](skills/biz-profile/README.md) | 다른 비즈니스 스킬이 재사용할 사업 프로필 인터뷰 | 사업 정보를 매번 다시 설명하지 않도록 기준 프로필을 만들 때 |
| [`biz-tax-team`](skills/biz-tax-team/README.md) | 영수증·지출 분류, 세금 계산 초안, 세무사 전달 패키지 | 경비와 증빙을 정리하거나 세무 상담을 준비할 때 |

### Public data — 공공데이터 조회 6개

| 스킬 | 조회 대상 | 결과 해석의 경계 |
|---|---|---|
| [`fsc-corporate-info`](skills/fsc-corporate-info/README.md) | 금융위원회 기업기본정보의 법인 개요 | 동명 법인은 사업자번호 등으로 추가 식별 |
| [`g2b-sanctioned-supplier`](skills/g2b-sanctioned-supplier/README.md) | 나라장터의 현재 유효한 부정당제재 | 결과 없음이 과거 제재 없음까지 뜻하지는 않음 |
| [`localdata-business-status`](skills/localdata-business-status/README.md) | 지방행정 인허가 업종의 영업·휴업·폐업 상태 | 동명 상호와 주소 후보를 사람이 확인 |
| [`national-pension-workplace`](skills/national-pension-workplace/README.md) | 국민연금 가입 사업장의 인원과 월별 변화 | 가입자 수를 전체 재직자 수로 단정하지 않음 |
| [`nts-business-registration`](skills/nts-business-registration/README.md) | 국세청 사업자등록 상태와 제출 정보 진위 | 상태조회와 진위확인은 입력·결과가 서로 다름 |
| [`nts-tax-delinquency`](skills/nts-tax-delinquency/README.md) | 국세청 공개 고액·상습체납자 명단 | 동명이인 가능성과 공개명단 범위를 명시 |

### Legal — 한국 법령 연결 1개

| 스킬 | 정확한 역할 | 먼저 사용하는 경우 |
|---|---|---|
| [`law-mcp-setup`](skills/law-mcp-setup/README.md) | Korean Law MCP 설치, 법제처 인증값 등록, 연결 복구와 검증 | 법률 스킬에서 최신 법령을 조회하거나 MCP 연결이 실패할 때 |

### Media — 영상 제작 5개

| 스킬 | 제작 단계 | 핵심 구분 |
|---|---|---|
| [`cinema-studio-pipeline`](skills/cinema-studio-pipeline/README.md) | 작품 기획부터 납품까지 | 승인·계보·연속성을 관리하는 **작품 제작 운영체계** |
| [`cinematic-video-pipeline`](skills/cinematic-video-pipeline/README.md) | 클립 생성과 로컬 후처리 | 이미지·영상 생성, 60fps 보간, 업스케일을 수행하는 **기술 파이프라인** |
| [`min-edit-seedance-2-0`](skills/min-edit-seedance-2-0/README.md) | 생성 입력 설계 | Seedance 2.0 멀티모달 프롬프트와 참조 역할 전문 |
| [`sync-cuts-to-music`](skills/sync-cuts-to-music/README.md) | 음악 기반 편집 | 실제 트랜지언트 분석과 검토 가능한 컷 패키지 전문 |
| [`timed-storyboard`](skills/timed-storyboard/README.md) | 쇼트·동선 프리프로덕션 | 초·프레임 단위 행동과 공간 제어 설계 전문 |

### Education — 학습 1개

| 스킬 | 정확한 역할 | 먼저 사용하는 경우 |
|---|---|---|
| [`adaptive-mastery-tutor`](skills/adaptive-mastery-tutor/README.md) | 선수지식 진단, 설명, 연습, 오개념 교정, 복습을 반복하는 개인 튜터 | 한 번의 답변이 아니라 단계별 수업과 이해 확인이 필요할 때 |

### Tooling — 스킬 제작 1개

| 스킬 | 정확한 역할 | 먼저 사용하는 경우 |
|---|---|---|
| [`skill-builder-101`](skills/skill-builder-101/README.md) | Codex 스킬 구조, 트리거, 참고자료 분리, MCP 연결과 패키징 안내 | 새로운 스킬을 처음 설계하거나 기존 스킬 구조를 정리할 때 |

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
