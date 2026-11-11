# 스킬 소스와 패키징

일반 사용자는 [관리형 설치기](../installation/00-index.md)를 사용합니다.
이 문서는 스킬을 수정하거나 `.skill` 파일로 배포하는 제작자를 위한 안내입니다.
작성 언어·frontmatter·참조 파일 규칙은 [스킬 작성 규칙](../skill-authoring.md)을 따릅니다.

## 소스 위치

| 경로 | 용도 |
|---|---|
| `skills/<name>/SKILL.md` | 스킬 설명과 작업별 참조 안내 |
| `skills/<name>/references/` | 필요한 작업에서만 읽는 상세 지침 |
| `refs/` | 출처·조사 기록·실행 예제. `.skill`에 포함하지 않음 |
| `prompts/` | 재사용 프롬프트 조각 |
| `dist/` | 생성한 `.skill` 파일. Git 추적에서 제외 |
| `AGENTS.md` | `build.sh --agents`로 생성하는 스킬 진입점 |

`skills/`의 원본을 수정합니다. 생성된 `AGENTS.md`나 설치된 사본을 원본처럼 관리하지 않습니다.
근거 자료를 추가하면 [refs 색인](../../refs/INDEX.md)에도 출처·조회 날짜·측정 환경을 남깁니다.

## 패키징 명령

저장소 루트에서 실행합니다. Bash와 coreutils, find, awk가 필요합니다.
압축에는 `zip` 또는 Python 3의 zipfile을 사용합니다.

```bash
bash build.sh                       # 전체 스킬을 dist/*.skill로 패키징
bash build.sh engineering-playbook  # 특정 스킬만 패키징
bash build.sh --check               # frontmatter·디렉터리 구조 검증
bash build.sh --agents              # AGENTS.md 재생성
bash build.sh --clean               # 생성한 dist/ 제거
bash build.sh --out /some/dir       # 산출물 경로 변경
```

`.skill`은 스킬 이름을 최상위 디렉터리로 갖는 ZIP 파일입니다.
`__pycache__`, `.DS_Store`, `node_modules` 등은 제외합니다.
배포할 때 패키징하며, 산출물은 필요하면 GitHub Release에 첨부합니다.

## 스킬만 연결하거나 복사하기

다음 명령은 Hub MCP를 등록하지 않는 제작용 도구입니다.

```bash
bash build.sh --link                       # ~/.claude/skills에 원본 심볼릭 링크
bash build.sh --install /path/to/project   # 프로젝트의 .claude/skills에 복사
```

링크는 원본 수정이 그대로 반영되므로 개인 스킬 제작에 유용합니다.
관리형 설치기는 심볼릭 링크를 덮어쓰지 않으므로 설치 방식을 바꿀 때는 기존 링크를 먼저 정리합니다.
프로젝트에 복사한 스킬은 팀과 공유하려면 커밋합니다. `--install`은 대상 스킬 디렉터리를 교체하므로
대상에서 수정한 내용은 먼저 보관하세요. 수정 파일 보호와 롤백이 필요하면 관리형 설치기를 사용합니다.

스킬 로딩 위치와 같은 이름의 스킬 우선순위는 에이전트마다 다릅니다.
지원 에이전트별 경로는 [설치 경로 표](../installation/01-agent-paths.md)를 확인하세요.

## 수정 후 확인

1. `skills/`의 소스와 해당 참조 안내를 함께 고칩니다.
2. `bash build.sh --check`와 `python3 -B scripts/check_docs.py`를 실행합니다.
3. 스킬 설명을 바꿨다면 `bash build.sh --agents`로 진입점을 갱신합니다.
4. 실제 작업에서 스킬이 선택되고 필요한 참조만 읽는지 확인합니다.
5. 관리형 설치를 사용한다면 업데이트하여 설치본에 반영합니다.
