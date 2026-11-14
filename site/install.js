'use strict';
const base = new URL('./', location.href);
const shellUrl = new URL('install.sh', base).href;
const windowsUrl = new URL('install.ps1', base).href;
const bundleUrl = new URL('joongi-skills.sigstore.jsonl', base).href;
const shellQuote = text => "'" + text.replaceAll("'", "'\\''") + "'";
const powerQuote = text => "'" + text.replaceAll("'", "''") + "'";
const revisionCode = "import json,re,urllib.request;u='https://api.github.com/repos/joongi007/joongi-skills';d=json.load(urllib.request.urlopen(u));assert d['id']==1452939341 and d['owner']['id']==68692377;s=json.load(urllib.request.urlopen(u+'/branches/main'))['commit']['sha'];assert re.fullmatch('[a-f0-9]{40}',s);print(s)";
const verifyPolicy = '--repo joongi007/joongi-skills --signer-workflow joongi007/joongi-skills/.github/workflows/pages.yml --source-ref refs/heads/main --deny-self-hosted-runners';
document.querySelector('#shell-command').textContent = `(set -eu\ninstall_dir=$(mktemp -d)\ntrap 'rm -rf -- "$install_dir"' EXIT\ncurl -fsSL ${shellQuote(shellUrl)} -o "$install_dir/install.sh"\ncurl -fsSL ${shellQuote(bundleUrl)} -o "$install_dir/attestation.jsonl"\nrevision=$(python3 -I -c ${shellQuote(revisionCode)})\ngh attestation verify "$install_dir/install.sh" --bundle "$install_dir/attestation.jsonl" ${verifyPolicy} --source-digest "$revision"\nbash "$install_dir/install.sh" install)`;
document.querySelector('#windows-command').textContent = `$ErrorActionPreference='Stop'\n$installDir=Join-Path $env:TEMP ([Guid]::NewGuid().ToString())\nNew-Item -ItemType Directory -Path $installDir | Out-Null\ntry {\n  Invoke-WebRequest ${powerQuote(windowsUrl)} -OutFile "$installDir\\install.ps1"\n  Invoke-WebRequest ${powerQuote(bundleUrl)} -OutFile "$installDir\\attestation.jsonl"\n  $repository=Invoke-RestMethod 'https://api.github.com/repos/joongi007/joongi-skills'\n  if ($repository.id -ne 1452939341 -or $repository.owner.id -ne 68692377) { throw 'Repository identity mismatch' }\n  $revision=(Invoke-RestMethod 'https://api.github.com/repos/joongi007/joongi-skills/branches/main').commit.sha\n  if ($revision -notmatch '^[a-f0-9]{40}$') { throw 'Invalid revision' }\n  gh attestation verify "$installDir\\install.ps1" --bundle "$installDir\\attestation.jsonl" ${verifyPolicy} --source-digest $revision\n  if ($LASTEXITCODE -ne 0) { throw 'Signature verification failed' }\n  powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$installDir\\install.ps1" install\n  if ($LASTEXITCODE -ne 0) { throw 'Installation failed' }\n} finally { Remove-Item -LiteralPath $installDir -Recurse -Force }`;
if (location.protocol !== 'https:') {
  document.querySelector('#shell-command').textContent = 'bash install.sh install --dry-run\nbash install.sh install';
  document.querySelector('#windows-command').textContent = '.\\install.ps1 install';
  const preview = document.createElement('p');
  preview.className = 'install-hint';
  preview.textContent = '로컬 미리보기입니다. 아래 명령은 클론한 저장소 루트에서 실행하세요. 공개 Pages 배포 후에는 이 위치에 다운로드 설치 명령이 표시됩니다.';
  document.querySelector('.install-box').prepend(preview);
  for (const link of document.querySelectorAll('a[download]')) link.hidden = true;
}
const tabs = [...document.querySelectorAll('[role=tab]')];
function activate(tab) {
  for (const item of tabs) {
    const selected = item === tab;
    item.setAttribute('aria-selected', String(selected));
    item.tabIndex = selected ? 0 : -1;
    document.getElementById(item.getAttribute('aria-controls')).hidden = !selected;
  }
}
for (const tab of tabs) {
  tab.addEventListener('click', () => activate(tab));
  tab.addEventListener('keydown', event => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const next = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs.at(-1) : tabs[(tabs.indexOf(tab) + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
      activate(next); next.focus();
    }
  });
}
for (const button of document.querySelectorAll('[data-copy]')) button.addEventListener('click', async () => {
  const text = document.getElementById(button.dataset.copy).textContent;
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = '복사됨 ✓';
    document.querySelector('#copy-notice').textContent = '설치 명령을 복사했습니다.';
    setTimeout(() => { button.textContent = '복사'; }, 2200);
  } catch {
    const range = document.createRange(); range.selectNodeContents(document.getElementById(button.dataset.copy));
    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    button.textContent = '선택됨';
    document.querySelector('#copy-notice').textContent = '명령이 선택되었습니다. 키보드로 복사하세요.';
  }
});
