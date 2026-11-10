# Download and inspect this script before running it. Python 3.10+ is required.
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)]
    [string]$Action = "install",
    [string]$DownloadBase = $env:JOONGI_DOWNLOAD_BASE,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$InstallArgs = @()
)
$ErrorActionPreference = "Stop"
$python = $null
$pythonArgs = @()
$candidates = if ($env:JOONGI_PYTHON) { @($env:JOONGI_PYTHON) } else { @("py", "python3", "python") }
foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
    $prefix = @()
    if ($candidate -eq "py") { $prefix = @("-3") }
    & $candidate @prefix -c "import sys; raise SystemExit(sys.version_info < (3, 10))" *> $null
    if ($LASTEXITCODE -eq 0) {
        $python = $candidate
        $pythonArgs = @($prefix)
        break
    }
}
if (-not $python) { throw "Python 3.10+ is required. Set JOONGI_PYTHON to its executable." }
$manager = Join-Path $PSScriptRoot "scripts/install_manager.py"
if (Test-Path $manager) {
    & $python @pythonArgs -B $manager $Action @InstallArgs
    exit $LASTEXITCODE
}
if (-not $DownloadBase) { $DownloadBase = "@DOWNLOAD_BASE@" }
if (-not $DownloadBase.StartsWith("https://")) {
    throw "Set -DownloadBase to your HTTPS GitHub Pages URL, or run from a clone."
}
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    # The same bounded, verified extraction code used by the POSIX bootstrap.
    $bootstrap = @'
import gzip, hashlib, io, json, os, pathlib, subprocess, sys, tarfile, urllib.request
if sys.version_info < (3, 10): raise SystemExit("Python 3.10+ is required")
base = sys.argv[1].rstrip('/') + '/'
target = pathlib.Path(sys.argv[2]).resolve()
with urllib.request.urlopen(base + 'bundle-manifest.json', timeout=30) as r:
    manifest = json.loads(r.read(65536))
with urllib.request.urlopen(base + 'joongi-skills.tar.gz', timeout=60) as r:
    data = r.read(32 * 1024**2 + 1)
if len(data) > 32 * 1024**2 or hashlib.sha256(data).hexdigest() != manifest.get('sha256'):
    raise SystemExit('Bundle size or SHA256 check failed')
with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
    unpacked = compressed.read(144 * 1024**2 + 1)
if len(unpacked) > 144 * 1024**2:
    raise SystemExit('Archive decompression limit exceeded')
with tarfile.open(fileobj=io.BytesIO(unpacked), mode='r:') as archive:
    members, total_size = [], 0
    for m in archive:
        members.append(m)
        total_size += m.size
        if len(members) > 10000 or total_size > 128 * 1024**2:
            raise SystemExit('Archive extraction limit exceeded')
    for m in members:
        out = target / m.name
        if not out.resolve().is_relative_to(target) or not (m.isfile() or m.isdir()) or m.issym() or m.islnk():
            raise SystemExit('Unsafe archive member')
    for m in members:
        out = target / m.name
        if m.isdir(): out.mkdir(parents=True, exist_ok=True)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(m) as stream: out.write_bytes(stream.read())
manager = target / 'joongi-skills/scripts/install_manager.py'
if not manager.is_file(): raise SystemExit('Bundle has no installer')
environment = dict(os.environ, JOONGI_INSTALL_DOWNLOAD_BASE=base.rstrip('/'))
raise SystemExit(subprocess.call([sys.executable, '-B', str(manager), *sys.argv[3:]], env=environment))
'@
    $bootstrap | & $python @pythonArgs -B - $DownloadBase $temporary $Action @InstallArgs
    $result = $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
exit $result
