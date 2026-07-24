# Biz + Korean Law for Codex

법제처 Korean Law MCP와 1인사업자용 Biz 스킬을 한 번에 설치하는 Codex 패키지입니다.

설치 프로그램이 다음 질문을 표시합니다.

```text
당신의 인증 코드는 무엇인가요?
> 본인의_OC_인증값
```

입력한 값은 법제처 국가법령정보센터 Open API의 `OC` 형식을 확인하고 실제 검색 연결을 시험한 뒤 사용자 컴퓨터에만 저장합니다. Git 저장소에는 기록하지 않습니다.

## 포함 항목

- `korean-law-mcp@4.8.0` 연결 런처
- Law MCP 연결·복구용 `law-mcp-setup` 스킬
- 8개 Biz 스킬
  - `biz-ai-secretary`
  - `biz-color-map`
  - `biz-finance-team`
  - `biz-health-check`
  - `biz-legal-team`
  - `biz-monthly-sop`
  - `biz-profile`
  - `biz-tax-team`
- `biz-health-check`에 필요한 6개 공공데이터 지원 스킬

Law MCP 서버 소스 자체를 복제해 넣지는 않습니다. 이 저장소의 연결 코드가 공식 npm 패키지 `korean-law-mcp`를 실행하고, 사용자가 입력한 `LAW_OC`를 프로세스 환경으로 안전하게 전달합니다.

## 준비 사항

- macOS 또는 Linux
- Python 3
- Node.js 20.19 이상
- Codex
- 법제처 Open API `OC` 인증값

인증값이 없다면 [국가법령정보 공동활용](https://open.law.go.kr)에서 Open API 사용을 신청하세요.

## 설치

```bash
git clone <이 저장소 주소>
cd biz-law-codex
python3 install.py
```

설치기가 인증값을 질문하면 본인의 `OC`를 입력합니다. 설치 후 Codex 앱을 다시 시작하거나 새 작업을 여세요.

Codex가 직접 연결하도록 하려면 플러그인을 불러온 뒤 다음처럼 요청할 수도 있습니다.

```text
Law MCP 연결해줘
```

그러면 `law-mcp-setup` 스킬이 인증값을 묻고 같은 설치·검증 절차를 진행합니다.

## 설치기가 하는 일

1. Node.js와 `npx` 버전을 확인합니다.
2. 법제처 API에 읽기 전용 검색 요청을 보내 연결 여부를 확인합니다.
3. 인증값을 `~/.codex/biz-law-codex/credentials.json`에 권한 `0600`으로 저장합니다.
4. Law MCP 런처를 `~/.codex/biz-law-codex/scripts/`에 설치합니다.
5. `~/.codex/config.toml`에 `korean-law` MCP를 등록합니다.
6. Biz 및 지원 스킬을 `~/.codex/skills/`에 설치합니다.
7. 기존 설정과 같은 이름의 스킬은 `~/.codex/backups/`에 백업합니다.

## 연결 확인

Codex를 다시 시작한 뒤 다음처럼 요청하세요.

```text
민법 제1조를 현재 법령 원문으로 찾아줘
```

법령 검색 도구가 실행되고 법제처 출처가 표시되면 연결된 것입니다.

## 인증값 보안

- 실제 인증값을 `.env`, README, 예제 파일 또는 Git 커밋에 넣지 마세요.
- 인증값은 사용자 컴퓨터의 Codex 폴더에만 저장됩니다.
- Law MCP 실행 시 인증값은 명령행 인수가 아니라 `LAW_OC` 환경변수로 전달됩니다.
- 인증값을 바꾸려면 `python3 install.py`를 다시 실행하세요.
- 법제처 기본 검색 API는 임의 문자열에도 검색 결과를 반환할 수 있어, 설치기는 `OC`의 실제 발급·소유 여부까지 보증하지 않습니다. 발급 여부는 법제처 마이페이지에서 확인하세요.

## 개발자용 검사

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_package.py
```

## 주의

이 패키지는 법률·세무·재무 전문가를 대신하지 않습니다. 법령과 수치는 조회 시점의 공식 원문을 다시 확인하고, 신고·서명·소송·대출 같은 중요한 결정은 해당 전문가와 검토하세요.
