# Native PowerShell + Windows Python integration, isolated under the checkout.
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$repository = Split-Path $PSScriptRoot -Parent
$temporary = Join-Path $repository (".test-windows-" + [Guid]::NewGuid().ToString("N"))
$testHome = Join-Path $temporary "home with spaces"
$powershell = (Get-Process -Id $PID).Path
$bootstrap = Join-Path $repository "install.ps1"
function Invoke-Installer([string]$Action, [string[]]$ExtraArgs = @()) {
    & $powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $bootstrap $Action --home $testHome @ExtraArgs
    if ($LASTEXITCODE -ne 0) { throw "Installer $Action failed ($LASTEXITCODE)" }
}
try {
    New-Item -ItemType Directory -Path $testHome | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $testHome ".codex") | Out-Null
    Invoke-Installer "install" @("--dry-run")
    if (Test-Path (Join-Path $testHome ".local")) { throw "Dry-run wrote files" }
    Invoke-Installer "install"
    $launcher = Join-Path $testHome ".local/bin/joongi-hub.cmd"
    & $launcher --version
    if ($LASTEXITCODE -ne 0) { throw "Installed Windows launcher failed" }
    $config = Join-Path $testHome ".codex/config.toml"
    if (-not (Select-String -LiteralPath $config -Pattern 'mcp_servers\."joongi-hub"' -Quiet)) { throw "Codex MCP absent" }
    New-Item -ItemType Directory -Path (Join-Path $testHome ".copilot") | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $testHome ".config/opencode") -Force | Out-Null
    Invoke-Installer "update"
    $copilot = Get-Content (Join-Path $testHome ".copilot/mcp-config.json") -Raw | ConvertFrom-Json
    if ($copilot.mcpServers.'joongi-hub'.type -ne "local") { throw "New Copilot agent not registered" }
    $opencode = Get-Content (Join-Path $testHome ".config/opencode/opencode.json") -Raw | ConvertFrom-Json
    if ($opencode.mcp.'joongi-hub'.command[-1] -ne "stdio") { throw "New OpenCode agent not registered" }
    Invoke-Installer "uninstall"
    if (Test-Path $launcher) { throw "Managed launcher survived uninstall" }
    $copilot = Get-Content (Join-Path $testHome ".copilot/mcp-config.json") -Raw | ConvertFrom-Json
    if ($copilot.mcpServers.PSObject.Properties.Name -contains 'joongi-hub') { throw "MCP survived uninstall" }
    Write-Output "Windows native smoke passed: dry-run, install, launcher, update, new agent detection, MCP registration, uninstall."
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
