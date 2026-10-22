[CmdletBinding()]
param(
    [string]$SourceDirectory = $env:D2_IMPORT_SOURCE,
    [Alias('DestinationRoot')][string]$GameDirectory = '',
    [switch]$CheckOnly,
    [switch]$Replace,
    [switch]$SkipRuntimeCheck
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose(); $stream.Dispose() }
}

function Assert-LocalOutput([string]$Path) {
    $ancestor = $Path
    while (-not [string]::IsNullOrWhiteSpace($ancestor)) {
        if (Test-Path -LiteralPath $ancestor) {
            if (((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw ('Linked output folders are not supported: ' + $ancestor)
            }
        }
        $ancestor = [IO.Path]::GetDirectoryName($ancestor)
    }
}

try {
    if ([string]::IsNullOrWhiteSpace($SourceDirectory)) { throw 'No game folder supplied. Run Import Game Assets.cmd and paste your installed Diablo II + LoD folder.' }
    $SourceDirectory = $SourceDirectory.Trim().Trim([char]34)
    $source = (Resolve-Path -LiteralPath $SourceDirectory).ProviderPath
    if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw 'Source must be a folder.' }
    if ([string]::IsNullOrWhiteSpace($GameDirectory)) { $GameDirectory = Split-Path -Parent $PSScriptRoot }
    $payload = [IO.Path]::GetFullPath($GameDirectory)
    $destination = Join-Path $payload 'gamedata'
    $sourcePrefix = $source.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if ($payload.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase) -or
        $source.StartsWith($payload.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $source.Equals($payload, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The original installation and adapter folders must be separate, with neither inside the other.'
    }
    Assert-LocalOutput $destination
    $hasExisting = (Test-Path -LiteralPath $destination) -and @(Get-ChildItem -LiteralPath $destination -Force).Count -gt 0
    if (-not $CheckOnly -and $hasExisting -and -not $Replace) { throw 'gamedata is not empty. Use -Replace to keep a backup and import again. Saves are never replaced.' }
    $profile = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'profiles\retail-enUS-1.14b.json') -Raw | ConvertFrom-Json
    $allowedNames = @('d2char.mpq','d2data.mpq','d2exp.mpq','d2music.mpq','d2sfx.mpq','d2speech.mpq',
        'd2video.mpq','d2xmusic.mpq','d2xtalk.mpq','d2xvideo.mpq','Patch_D2.mpq','D2.LNG')
    if (@($profile.files).Count -ne 12 -or
        @(Compare-Object ($profile.files.name | Sort-Object) ($allowedNames | Sort-Object)).Count -ne 0) { throw 'Invalid resource import profile.' }
    $entries = @(Get-ChildItem -LiteralPath $source -File)
    $verified = @()
    foreach ($expected in $profile.files) {
        $matches = @($entries | Where-Object { $_.Name -ieq $expected.name })
        if ($matches.Count -ne 1) { throw ('Missing required file: ' + $expected.name + '. Select the installed Diablo II + LoD folder, not an installer or Resurrected.') }
        $file = $matches[0]
        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw ('Linked source is not supported: ' + $file.Name) }
        if ($file.Length -ne $expected.size) { throw ('Unsupported resource size: ' + $file.Name + '. Supported profile: enUS 1.14b.') }
        Write-Host ('Checking original ' + $file.Name)
        $hash = Get-Sha256 $file.FullName
        if ($hash -ne $expected.sha256) { throw ('Unsupported or modified resource: ' + $file.Name + '. No resources were imported.') }
        $verified += [pscustomobject]@{ name=$expected.name; size=$file.Length; sha256=$hash; source=$file.FullName }
    }
    $runtime = Get-Content -LiteralPath (Join-Path $payload 'runtime-manifest.json') -Raw | ConvertFrom-Json
    $externalCore = ($null -ne $runtime.PSObject.Properties['externalCoreRequired']) -and [bool]$runtime.externalCoreRequired
    if ($externalCore) {
        $splitDirectory = Join-Path $PSScriptRoot 'chinese-patch'
        $splitManifest = Join-Path $splitDirectory 'split-manifest.json'
        if (-not (Test-Path -LiteralPath $splitManifest -PathType Leaf)) { throw 'Extract the separate Chinese patch ZIP into the same card root before importing.' }
        $split = Get-Content -LiteralPath $splitManifest -Raw | ConvertFrom-Json
        $patchProfile = [pscustomobject]@{ size=$split.sourceMpq.bytes; sha256=$split.sourceMpq.sha256 }
        if ($patchProfile.sha256 -ne 'dacbd6dea63ed9591bf6697c54e30224b07edf64dfb55235c70f5c7679bc67ea') { throw 'Unsupported Chinese patch supplement.' }
        foreach ($entry in $runtime.supplementFiles.PSObject.Properties) {
            $relative = $entry.Name
            if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)' -or $relative.Contains(':')) { throw 'Unsafe supplement manifest path.' }
            $file = Join-Path $splitDirectory $relative
            if ((Get-Item -LiteralPath $file).Length -ne $entry.Value.size -or (Get-Sha256 $file) -ne $entry.Value.sha256) { throw ('Damaged Chinese supplement: ' + $relative) }
        }
        $python = Join-Path $PSScriptRoot 'python\python.exe'
    }
    else {
        $patchProfile = Get-Content -LiteralPath (Join-Path $payload 'patches\zh-CN\patch-manifest.json') -Raw | ConvertFrom-Json
        $patchPath = Join-Path $payload 'patches\zh-CN\Patch_D2.mpq'
        if ((Get-Item -LiteralPath $patchPath).Length -ne $patchProfile.size -or (Get-Sha256 $patchPath) -ne $patchProfile.sha256) { throw 'Bundled community Chinese patch is missing or damaged. Re-extract the complete adapter ZIP.' }
    }
    $frontendEnabled = ($null -ne $runtime.PSObject.Properties['frontendResourceGeneration']) -and [bool]$runtime.frontendResourceGeneration
    if (-not $SkipRuntimeCheck) {
        Write-Host 'Checking included offline runtime and ARM engine...'
        foreach ($entry in $runtime.files.PSObject.Properties) {
            $relative = $entry.Name
            if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)' -or $relative.Contains(':')) { throw 'Unsafe runtime manifest path.' }
            $file = Join-Path $payload $relative
            if ((Get-Item -LiteralPath $file).Length -ne $entry.Value.size -or (Get-Sha256 $file) -ne $entry.Value.sha256) { throw ('Damaged adapter runtime: ' + $relative) }
        }
    }
    if ($externalCore) {
        $coreArguments = @((Join-Path $PSScriptRoot 'prepare_external_core.py'), '--payload', $payload)
        if ($CheckOnly) { $coreArguments += '--check-only' }
        & $python @coreArguments
        if ($LASTEXITCODE -ne 0) { throw 'Player-supplied core preparation failed.' }
        if ($CheckOnly) {
            $temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('d2-chinese-check-' + [guid]::NewGuid().ToString('N'))
            Assert-LocalOutput $temporaryRoot
            [IO.Directory]::CreateDirectory($temporaryRoot) | Out-Null
            $checkPatch = Join-Path $temporaryRoot 'Patch_D2.mpq'
            & $python (Join-Path $PSScriptRoot 'mpq_split.py') --stormlib (Join-Path $PSScriptRoot 'stormlib\x64\StormLib.dll') rebuild --bundle $splitDirectory --source $source --output $checkPatch
            if ($LASTEXITCODE -ne 0) { throw 'Chinese patch reconstruction check failed.' }
            [IO.File]::Delete($checkPatch)
            [IO.Directory]::Delete($temporaryRoot, $false)
        }
    }
    Write-Host 'Original resources and Chinese patch inputs verified.'
    if ($CheckOnly) { exit 0 }
    [IO.Directory]::CreateDirectory($payload) | Out-Null
    $stage = Join-Path $payload ('gamedata.import-' + [guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    $backup = $null
    try {
        $copyRecords = @()
        foreach ($file in @($verified | Where-Object { $_.name -ine 'Patch_D2.mpq' })) {
            Write-Host ('Importing ' + $file.name)
            $target = Join-Path $stage $file.name
            [IO.File]::Copy($file.source, $target, $false)
            if ((Get-Sha256 $target) -ne $file.sha256) { throw ('Copy checksum mismatch: ' + $file.name) }
            $copyRecords += [pscustomobject]@{ name=$file.name; size=$file.size; sha256=$file.sha256; origin='user-install' }
        }
        Write-Host 'Preparing Chinese patch...'
        if ($externalCore) {
            & $python (Join-Path $PSScriptRoot 'mpq_split.py') --stormlib (Join-Path $PSScriptRoot 'stormlib\x64\StormLib.dll') rebuild --bundle $splitDirectory --source $source --output (Join-Path $stage 'Patch_D2.mpq')
            if ($LASTEXITCODE -ne 0) { throw 'Chinese patch reconstruction failed; previous gamedata and saves are unchanged.' }
        }
        else { [IO.File]::Copy($patchPath, (Join-Path $stage 'Patch_D2.mpq'), $false) }
        if ((Get-Sha256 (Join-Path $stage 'Patch_D2.mpq')) -ne $patchProfile.sha256) { throw 'Chinese patch copy checksum mismatch.' }
        $patchOrigin = if ($externalCore) { 'rebuilt-from-separate-chinese-bundle-and-user-install' } else { 'bundled-community-zh-CN' }
        $copyRecords += [pscustomobject]@{ name='Patch_D2.mpq'; size=$patchProfile.size; sha256=$patchProfile.sha256; origin=$patchOrigin }
        $manifestSchema = 2
        if ($frontendEnabled) {
            Write-Host 'Extracting frontend environment from your original MPQ...'
            $architecture = if ([IntPtr]::Size -eq 8) { 'x64' } else { 'Win32' }
            $nativeDirectory = Join-Path $PSScriptRoot ('stormlib\' + $architecture)
            $env:PATH = $nativeDirectory + [IO.Path]::PathSeparator + $env:PATH
            if (-not ('D2FrontendAssets' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'FrontendAssets.cs') }
            $environmentPath = Join-Path $stage 'frontend-environment.bgra'
            [D2FrontendAssets]::Generate($source, $environmentPath)
            $environmentFile = Get-Item -LiteralPath $environmentPath
            if ($environmentFile.Length -ne 1920000) { throw 'Invalid generated frontend environment.' }
            $environmentHash = Get-Sha256 $environmentPath
            if ($null -ne $profile.PSObject.Properties['frontendEnvironmentSha256'] -and $environmentHash -ne $profile.frontendEnvironmentSha256) { throw 'Generated frontend environment does not match this supported original profile.' }
            $copyRecords += [pscustomobject]@{ name='frontend-environment.bgra'; size=$environmentFile.Length; sha256=$environmentHash; origin='derived-from-user-d2data' }
            $manifestSchema = 3
        }
        $totalBytes = [long](($copyRecords | Measure-Object -Property size -Sum).Sum)
        $report = [ordered]@{
            schema=$manifestSchema; profile=$profile.id; importedAt=[DateTimeOffset]::Now.ToString('o')
            validation='static-checks-passed'; deviceTested=$false
            language='zh-CN'; runtimeTarget='LoD 1.13d ARM RGDSplus dualscreen'
            copiedBytes=$totalBytes; files=$copyRecords; engineSha256=$runtime.engineSha256
            originalPatchSha256=(@($verified | Where-Object { $_.name -ieq 'Patch_D2.mpq' }))[0].sha256
        }
        [IO.File]::WriteAllText((Join-Path $stage 'resource-manifest.json'), ($report | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
        if (Test-Path -LiteralPath $destination) {
            Assert-LocalOutput $destination
            if (@(Get-ChildItem -LiteralPath $destination -Force).Count -eq 0) {
                # Remove only the checked empty directory supplied by the ZIP.
                # This is non-recursive and fails if anything was added to it.
                [IO.Directory]::Delete($destination, $false)
            }
            else {
                $backup = Join-Path $payload ('gamedata.backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
                Assert-LocalOutput $backup
                [IO.Directory]::Move($destination, $backup)
            }
        }
        try { [IO.Directory]::Move($stage, $destination) }
        catch {
            if ($backup -and -not (Test-Path -LiteralPath $destination)) { [IO.Directory]::Move($backup, $destination) }
            throw
        }
    }
    catch { Write-Warning ('Incomplete import retained for inspection: ' + $stage); throw }
    Write-Host ('Import complete: ' + $destination)
    if ($backup) { Write-Host ('Previous gamedata retained at: ' + $backup) }
    Write-Host 'Original PC installation and adapter saves were not changed.'
    Write-Host 'Safely eject the card, then launch Diablo II for RGDSplus from the Ports menu. No runtime downloads are needed.'
    exit 0
}
catch { Write-Error $_ -ErrorAction Continue; exit 1 }
