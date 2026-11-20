$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Security
    $root = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) ('joongi-hub\edge\' + 'CONNECTION_ID')
    if ((Get-Item -LiteralPath $root).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point' }
    $sealed = [IO.File]::ReadAllBytes((Join-Path $root 'descriptor.dpapi'))
    $plain = [Security.Cryptography.ProtectedData]::Unprotect($sealed, $null, 'CurrentUser')
    $sha = [Security.Cryptography.SHA256]::Create()
    $fingerprint = ([BitConverter]::ToString($sha.ComputeHash($plain))).Replace('-','').ToLowerInvariant()
    if ($fingerprint -cne 'PUBLIC_FINGERPRINT') { throw 'Descriptor changed' }
    $descriptor = [Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json
    foreach ($file in $descriptor.files.PSObject.Properties) {
        $path = Join-Path $root $file.Name
        $item = Get-Item -LiteralPath $path
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point' }
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file.Value) { throw 'Runtime changed' }
    }
    foreach ($item in Get-ChildItem -LiteralPath $root -Recurse -Force) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point' }
        if (!$item.PSIsContainer) {
            $relative = $item.FullName.Substring($root.Length + 1).Replace('\','/')
            if ($relative -ne 'descriptor.dpapi' -and !$descriptor.files.PSObject.Properties[$relative]) { throw 'Unexpected runtime file' }
        }
    }
    $python = $descriptor.python
    if ((Get-FileHash -LiteralPath $python -Algorithm SHA256).Hash.ToLowerInvariant() -cne $descriptor.python_hash) { throw 'Python changed' }
    $signature = Get-AuthenticodeSignature -LiteralPath $python
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Python Software Foundation(?:,|$)') { throw 'Untrusted Python' }
    # The prepared worker is trusted code. No command, path, environment or script comes from a registry entry.
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $python
    $info.Arguments = '-I -S -B "' + (Join-Path $root 'worker.py') + '" "' + $root + '"'
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.WorkingDirectory = $root
    $keep = @('SystemRoot','WINDIR','USERPROFILE','LOCALAPPDATA','APPDATA','TEMP','TMP','PATH','ProgramFiles','ProgramFiles(x86)')
    foreach ($key in @($info.EnvironmentVariables.Keys)) { if ($keep -notcontains $key) { $info.EnvironmentVariables.Remove($key) } }
    $process = [Diagnostics.Process]::Start($info)
    # Windows ConsoleStream ReadAsync can block synchronously. Dedicated .NET workers
    # pump both directions without waiting for stdin EOF or requiring a PS runspace.
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
public static class JoongiEdgePipe {
    private static void Pump(Stream source, Stream destination) {
        byte[] buffer = new byte[8192];
        int size;
        while ((size = source.Read(buffer, 0, buffer.Length)) > 0) {
            destination.Write(buffer, 0, size);
            destination.Flush(); // Requests must reach Python before the owner closes stdin.
        }
    }
    public static int Run(Process process) {
        Task input = Task.Run(() => {
            try { Pump(Console.OpenStandardInput(), process.StandardInput.BaseStream); }
            catch (IOException) {} finally { process.StandardInput.Close(); }
        });
        Task output = Task.Run(() => Pump(process.StandardOutput.BaseStream, Console.OpenStandardOutput()));
        Task error = Task.Run(() => process.StandardError.BaseStream.CopyTo(Stream.Null));
        while (!process.HasExited && !input.IsCompleted) Thread.Sleep(50);
        if (!process.WaitForExit(20000)) { process.Kill(); process.WaitForExit(); }
        output.Wait();
        return process.ExitCode;
    }
}
'@
    exit [JoongiEdgePipe]::Run($process)
} catch {
    [Console]::Error.WriteLine('Personal Edge runtime unavailable or changed. Prepare and register it again.')
    exit 1
}
