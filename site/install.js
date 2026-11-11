'use strict';
const base = new URL('./', location.href);
const shellUrl = new URL('install.sh', base).href;
const windowsUrl = new URL('install.ps1', base).href;
const shellQuote = text => "'" + text.replaceAll("'", "'\\''") + "'";
const powerQuote = text => "'" + text.replaceAll("'", "''") + "'";
document.querySelector('#shell-command').textContent = `curl -fsSL ${shellQuote(shellUrl)} -o /tmp/joongi-install.sh\nbash /tmp/joongi-install.sh install`;
document.querySelector('#windows-command').textContent = `Invoke-WebRequest ${powerQuote(windowsUrl)} -OutFile "$env:TEMP\\joongi-install.ps1"\npowershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$env:TEMP\\joongi-install.ps1" install`;
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
