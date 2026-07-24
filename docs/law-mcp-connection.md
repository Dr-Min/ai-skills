# Law MCP 연결 구조

## `OC`가 필요한 이유

법제처 국가법령정보센터 Open API의 `lawSearch.do`와 `lawService.do` 요청에는 신청자 인증값인 `OC`가 필요합니다. 예를 들어 사용자의 인증값이 `honggildong`이라면 API 클라이언트는 내부적으로 `LAW_OC=honggildong`을 사용합니다.

`010103`만 입력하는 것이 아니라 법제처에 등록된 전체 인증값을 입력해야 합니다.

## 이 저장소의 역할

이 저장소는 Law MCP 서버를 새로 구현하지 않습니다.

- MCP 구현: [`korean-law-mcp`](https://github.com/chrisryugj/korean-law-mcp)
- 공식 데이터: [국가법령정보 공동활용](https://open.law.go.kr)
- 연결 코드: `scripts/law_mcp_launcher.py`
- 설치·검증 코드: `scripts/setup.py`

설치기는 사용자의 `OC` 형식과 법제처 검색 연결을 확인하고 로컬 자격정보 파일에 저장합니다. 런처는 MCP를 실행할 때만 이 값을 읽어 `LAW_OC` 환경변수로 전달합니다.

법제처 기본 검색 API는 임의의 비어 있지 않은 `OC`에도 결과를 반환할 수 있습니다. 따라서 자동 설치기는 검색 연결은 시험할 수 있지만, 해당 값의 실제 발급·소유 여부까지 판정할 수는 없습니다. 발급 여부는 법제처 마이페이지에서 별도로 확인해야 합니다.

```mermaid
flowchart LR
    U["사용자 OC 입력"] --> V["형식 확인 + 법제처 연결 시험"]
    V --> C["로컬 credentials.json (0600)"]
    C --> L["Law MCP 런처"]
    L --> M["korean-law-mcp"]
    M --> O["법제처 Open API"]
    X["Codex"] <--> M
```

## 저장 위치

| 항목 | 기본 위치 |
|---|---|
| 인증값 | `~/.codex/biz-law-codex/credentials.json` |
| MCP 런처 | `~/.codex/biz-law-codex/scripts/law_mcp_launcher.py` |
| Codex MCP 설정 | `~/.codex/config.toml` |
| 스킬 | `~/.codex/skills/` |
| 자동 백업 | `~/.codex/backups/biz-law-codex-*` |

## 실패 처리

- 법제처가 요청을 명시적으로 거부하면 설정을 쓰기 전에 설치를 중단합니다.
- 법제처 서버나 네트워크가 일시적으로 응답하지 않으면 경고를 남기고 설치를 계속합니다.
- 기존 `korean-law` MCP 설정은 백업한 뒤 이 패키지의 설정으로 교체합니다.
- 다른 MCP 설정과 Codex 설정은 그대로 보존합니다.
