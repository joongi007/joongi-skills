# 실행 전에 서명을 확인하는 보안 설치

간편 설치는 HTTPS로 받은 최초 스크립트를 바로 실행하고, 그 스크립트가 설치 번들을 검증합니다.
이 방식은 **최초 스크립트도 실행 전에 검증**합니다. 공식 GitHub CLI의 `gh attestation verify`,
Python 3.10 이상, HTTPS 다운로드가 가능한 환경이 필요합니다. 관리자 권한은 필요하지 않습니다.

| 방식 | 최초 스크립트 신뢰 | 설치 번들 서명 검증 |
|---|---|---|
| [간편 설치](00-index.md#클론-없이-설치) | HTTPS 다운로드 후 바로 실행 | 필수 |
| 이 문서의 보안 설치 | GitHub CLI로 서명·workflow·main 커밋을 실행 전 확인 | 필수 |
| 로컬 클론 설치 | 사용자가 선택·검토한 로컬 소스를 신뢰 | 원격 파일을 받지 않으므로 원격 검증 대상 없음 |

아래 명령 전체를 실행합니다. 검증 실패 시 실행을 중단하며 `--dry-run`을 사용하려면
마지막 설치 실행의 `install` 뒤에 추가합니다. 배포 중에는 main과 Pages가 잠시 다를 수 있으므로
최신 [Pages 배포](https://github.com/joongi007/joongi-skills/actions/workflows/pages.yml) 완료 후 다시 시도하세요.

## macOS · Linux · WSL

```bash
(set -eu
install_dir=$(mktemp -d)
trap 'rm -rf -- "$install_dir"' EXIT
curl -fsSL 'https://joongi007.github.io/joongi-skills/install.sh' -o "$install_dir/install.sh"
curl -fsSL 'https://joongi007.github.io/joongi-skills/joongi-skills.sigstore.jsonl' -o "$install_dir/attestation.jsonl"
revision=$(python3 -I -c 'import json,re,urllib.request;u='\''https://api.github.com/repos/joongi007/joongi-skills'\'';d=json.load(urllib.request.urlopen(u));assert d['\''id'\'']==1452939341 and d['\''owner'\'']['\''id'\'']==68692377;s=json.load(urllib.request.urlopen(u+'\''/branches/main'\''))['\''commit'\'']['\''sha'\''];assert re.fullmatch('\''[a-f0-9]{40}'\'',s);print(s)')
gh attestation verify "$install_dir/install.sh" --bundle "$install_dir/attestation.jsonl" --repo joongi007/joongi-skills --signer-workflow joongi007/joongi-skills/.github/workflows/pages.yml --source-ref refs/heads/main --deny-self-hosted-runners --source-digest "$revision"
bash "$install_dir/install.sh" install)
```

## Windows PowerShell

```powershell
$ErrorActionPreference='Stop'
$installDir=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) ('joongi-install-'+[Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $installDir | Out-Null
try {
  Invoke-WebRequest 'https://joongi007.github.io/joongi-skills/install.ps1' -OutFile "$installDir\install.ps1"
  Invoke-WebRequest 'https://joongi007.github.io/joongi-skills/joongi-skills.sigstore.jsonl' -OutFile "$installDir\attestation.jsonl"
  $repository=Invoke-RestMethod 'https://api.github.com/repos/joongi007/joongi-skills'
  if ($repository.id -ne 1452939341 -or $repository.owner.id -ne 68692377) { throw 'Repository identity mismatch' }
  $revision=(Invoke-RestMethod 'https://api.github.com/repos/joongi007/joongi-skills/branches/main').commit.sha
  if ($revision -notmatch '^[a-f0-9]{40}$') { throw 'Invalid revision' }
  gh attestation verify "$installDir\install.ps1" --bundle "$installDir\attestation.jsonl" --repo joongi007/joongi-skills --signer-workflow joongi007/joongi-skills/.github/workflows/pages.yml --source-ref refs/heads/main --deny-self-hosted-runners --source-digest $revision
  if ($LASTEXITCODE -ne 0) { throw 'Signature verification failed' }
  powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$installDir\install.ps1" install
  if ($LASTEXITCODE -ne 0) { throw 'Installation failed' }
} finally { Remove-Item -LiteralPath $installDir -Recurse -Force }
```

자식 PowerShell의 실행 정책만 지정하며 사용자 전역 정책은 바꾸지 않습니다.
임시 폴더는 성공·실패 후 정리됩니다. 명령의 저장소·workflow·주소를 임의 URL로 바꾸면
동일한 신뢰 정책을 유지한다고 볼 수 없습니다.

이 검증은 배포 파일의 출처와 일치 여부를 확인합니다. 코드 자체에 취약점이 없다는 보안 인증은 아닙니다.
[세부 신뢰 경계](../operations/10-security-boundaries.md#다운로드-실행-전-서명-검증) ·
[설치 후 첫 사용](../getting-started/00-index.md) · [오류 해결](00-index.md#설치가-안-될-때).
