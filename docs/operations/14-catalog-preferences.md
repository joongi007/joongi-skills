# 검색 범위·출처·묶음·사용 통계

스킬을 회사·개인·공개 출처로 구분하고 현재 작업에서 필요한 지침만 사용하도록 선택합니다.
이 설정은 단일 사용자 Hub의 카탈로그 선호이며 OS 접근 제어나 회사 정책을 강제하는 보안 시스템이 아닙니다.
다른 이름으로 직접 등록한 MCP와 에이전트가 자체적으로 읽는 전역 스킬은 별도로 관리합니다.

## 관리 화면에서 선택하기

통합 검색의 **검색 범위 설정** 또는 **검색 설정** 메뉴를 엽니다.
현재 작업 범위에서 개발·문서·디자인·도구 묶음, 개별 스킬·MCP, 출처를 선택한 뒤 저장합니다.
묶음 선택은 현재 범위의 모든 출처에 적용됩니다. 회사 출처도 디자인 분류라면 디자인 묶음을 끌 때 함께 제외됩니다.
기본 디자인만 끄고 회사 디자인을 남기려면 개별 기본 스킬을 끄고 회사 출처를 켜세요.
여러 묶음에 속한 항목은 그 중 하나를 끄면 제외됩니다. 예를 들어 engineering-playbook은 개발·문서,
creating-diagrams는 디자인·문서, building-procedural-3d는 디자인·개발에 속합니다.

선택을 끈 스킬은 검색·상세·본문·resource·native Skills 목록에서 제외됩니다.
MCP를 끄면 해당 서버의 검색·native 도구 목록과 원격 스킬 조회에서 제외됩니다.
이미 알고 있는 도구 ID의 직접 호출까지 차단하는 인가 정책은 아닙니다. 직접 호출은 기존 인증·호출 승인·실행 격리를 따릅니다.
서버 자체를 사용하지 못하게 하려면 연결 비활성화 또는 별도 호출 차단 정책을 사용하세요.
파일을 삭제하거나 이미 설치한 에이전트의 스킬 사본을 자동 제거하는 기능은 아닙니다.
실행 중인 외부 프로세스나 이미 시작한 작업의 취소를 의미하지도 않습니다.

설정은 상태 저장소의 `catalog-preferences.json`에 저장하며 공용과 프로젝트가 각각 가집니다.
프로젝트의 공용 항목 선택/로컬 스킬 우선순위에 현재 범위의 선호를 추가 적용합니다.
native 목록을 읽는 에이전트는 설정 변경 후 MCP 연결을 다시 열어 갱신합니다.

## 출처별 폴더 등록

기본 배포 스킬은 `builtin`, 프로젝트 자체 스킬은 `project` 출처입니다.
별도 로컬 폴더는 고유 ID와 표시 이름으로 등록합니다. 지정할 폴더 바로 아래에 스킬별 디렉터리가 있어야 합니다.

```text
/path/to/company-skills/
  design-guide/SKILL.md
  code-review/SKILL.md
/path/to/personal-skills/
  writing-guide/SKILL.md
```

회사 출처의 ID가 `company`라면 스킬 이름은 `company__design-guide`가 됩니다.
프로젝트 파일을 공용 폴더로 옮기거나 회사 스킬을 공개 배포하는 작업이 아닙니다.
출처 ID와 기존 MCP 서버 ID가 충돌하면 등록을 거절합니다. 정확한 항목 이름이 모호한 경우에도 임의로 선택하지 않습니다.
등록은 로컬 읽기 경로를 추가하는 행동입니다. 다른 사람의 스킬은 출처·라이선스·내용을 먼저 검토합니다.
절대 경로만 받고 symlink·경로 이탈을 거절합니다. 스킬 디렉터리의 기존 파일·크기 제한도 유지합니다.
출처 목록은 최대 32개이며 회사·개인 폴더 경로를 MCP 상태 응답에 반환하지 않습니다.

## 에이전트에서 요청하기

> 이 프로젝트에서 기본 디자인 스킬은 끄고 회사 디자인 출처를 사용하도록 설정해줘.

로컬 stdio와 로컬 credential bridge의 owner 연결에서 사용자의 요청을 받아 `hub_catalog_configure`를 사용할 수 있습니다.
직접 HTTP MCP·App callback·원격 서버가 같은 이름의 도구를 호출해 관리 설정을 바꾸지는 못합니다.
HTTP MCP로는 상태·상세·통계를 조회할 수 있고, 변경은 인증한 로컬 관리 화면에서 수행합니다.
설정 경계는 OS 사용자와 Hub 본체를 신뢰합니다. 같은 권한의 악성 로컬 프로그램을 격리하지는 않습니다.

```text
hub_catalog_status()
hub_catalog_configure(patch={"disabled":{"skill":["applying-design-systems","creating-diagrams","building-procedural-3d"]}})
```

묶음 전체를 끄는 예시는 `patch={"disabled":{"category":["design"]}}`입니다.
`disabled`의 배열은 지정한 종류 전체를 교체합니다. 예를 들어 기존에 개발도 꺼져 있었다면
`["development","design"]`처럼 유지할 항목을 함께 보내야 합니다. 생략한 다른 종류의 배열은 유지합니다.
사용할 수 있는 분류 ID는 `development`, `documentation`, `design`, `tools`입니다.
`category_overrides`는 `skill:company__design-guide` 또는 `server:서버ID`를 키로 분류 배열을 지정합니다.
외부 MCP는 기본 도구 분류에 속하며 필요하면 서버 단위로 바꿉니다.

출처 등록 예시는 다음과 같습니다. `/path/to/company-skills`를 실제 존재하는 경로로 바꾸고
`sources` 배열에 유지할 기존 출처도 함께 포함합니다.

```json
{"patch":{"sources":[{"id":"company","name":"회사 스킬","path":"/path/to/company-skills","enabled":true,"category":"design"}]}}
```

## 회사 기본값과 native 설치 구분

Hub에서 스킬을 끄더라도 에이전트의 native 스킬 폴더에 이미 설치된 사본은 남습니다.
기본 디자인 스킬을 native로 설치하지 않으려면 설치 명령에 다음 옵션을 붙입니다.
클론의 저장소 루트에서 실행하는 Bash 예시입니다.

```bash
bash install.sh install --exclude-category design
bash install.sh update --exclude-category documentation
bash install.sh update --reset-skill-selection
```

첫 명령의 제외는 설치 manifest에 저장되며 업데이트·새 에이전트 감지에도 유지됩니다.
추가 `--exclude-category`는 기존 제외에 누적되고 반복해 여러 종류를 지정할 수 있습니다.
`--reset-skill-selection`은 저장 제외를 비운 뒤 같은 명령에 새로 지정한 제외를 적용합니다.
카탈로그 설정과 설치 선택은 별개이며 한쪽의 초기화가 다른 쪽을 바꾸지 않습니다.

이미 설치된 제외 대상은 이 설치기가 관리하고 사용자가 수정하지 않은 사본만 제거합니다.
회사나 다른 도구 소유 파일·사용자 수정본은 보존하고 경로를 안내합니다. 복원도 그 파일을 강제로 덮어쓰지 않습니다.
허브 카탈로그에는 원본이 남으므로 필요한 경우 별도로 카탈로그 선택도 끄세요.
[설치·업데이트 상세](../installation/00-index.md).

## 선택형 사용 통계

통계는 **기본 꺼짐**입니다. 켜면 해당 범위의 `usage-stats.sqlite3`에 일별 종류·항목 ID·결과·횟수와
총/최대 처리 시간을 집계합니다. 검색어 원문·호출 인수·응답 본문·토큰·개인 경로는 기록하지 않습니다.
스킬/도구 ID 자체에도 회사 내부 정보가 들어갈 수 있으므로 이 파일을 공개하지 않습니다.
외부 분석 서버로 전송하지 않습니다.

```text
hub_catalog_configure(patch={"usage_enabled":true})
hub_catalog_usage()
hub_catalog_usage_reset()
```

기록·조회 때 최근 30일과 최대 1,000개 집계 키로 정리합니다. 통계를 끄면 새 기록을 멈추지만
이전 집계를 삭제하지는 않습니다. 삭제는 별도의 통계 초기화를 사용합니다.
집계 실패가 실제 도구 호출 결과를 실패로 바꾸지는 않습니다. 통계는 전체 실행 감사 기록이나 과금 계측이 아닙니다.

## 초기화·진단

`hub_catalog_reset`은 현재 범위의 선호만 기본값으로 돌립니다. 추가 출처·분류·비활성 선택을 지우고
search-first·통계 꺼짐으로 돌아가며 스킬 파일·MCP 등록·인증·기존 통계·native 설치 선택은 삭제하지 않습니다.
통계 초기화는 별도 동작이고 local stdio owner 또는 인증한 관리 화면에서만 실행합니다.

| 접점 | 조회 | 변경 |
|---|---|---|
| MCP | `hub_catalog_status`, `hub_get_item`, `hub_catalog_usage` | 로컬 stdio/credential bridge owner의 configure/reset/usage_reset |
| 관리 API | `GET /api/v1/catalog/settings`, `/item`, `/usage` | 인증한 관리 화면의 settings/reset/usage/reset POST |

상태에는 metadata 준비 캐시의 프로세스별 hit/miss와 한도가 포함됩니다.
이 캐시 카운터와 선택형 사용 통계는 서로 다른 진단 정보입니다.
고급 노출 방식 `all-native`는 현재 선택한 서버의 모든 도구를 native 목록에 노출합니다.
기본 `search-first`로 돌아가려면 해당 값을 저장하거나 카탈로그 선호를 초기화합니다.
