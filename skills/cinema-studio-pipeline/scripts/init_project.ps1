[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Low')]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]+(?:-[a-z0-9]+)*$')]
    [string]$ProjectId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Z][A-Z0-9]{1,5}$')]
    [string]$ProjectPrefix,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Title,

    [string]$TemplateRoot,

    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$MaxInitInputBytes = 32 * 1024 * 1024

$runtimeScriptRoot = [string]$PSScriptRoot
if ([string]::IsNullOrWhiteSpace($runtimeScriptRoot) -and $MyInvocation.MyCommand.Path) {
    $runtimeScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($runtimeScriptRoot)) {
    throw 'Unable to resolve the init_project.ps1 script directory'
}
if ([string]::IsNullOrWhiteSpace($TemplateRoot)) {
    $TemplateRoot = Join-Path $runtimeScriptRoot '..\templates'
}

function Get-NormalizedFullPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)).TrimEnd('\', '/')
}

function Test-IsEqualOrDescendant {
    param(
        [Parameter(Mandatory = $true)][string]$Candidate,
        [Parameter(Mandatory = $true)][string]$Base
    )
    if ($Candidate.Equals($Base, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    $prefix = $Base.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    return $Candidate.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-NoReparsePointInExistingPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $fullPath = Get-NormalizedFullPath -Path $Path
    $pathRoot = [System.IO.Path]::GetPathRoot($fullPath)
    $current = $pathRoot
    $relative = $fullPath.Substring($pathRoot.Length).TrimStart('\', '/')
    $segments = @($relative -split '[\\/]' | Where-Object { $_ })
    for ($segmentIndex = 0; $segmentIndex -lt $segments.Count; $segmentIndex++) {
        $segment = $segments[$segmentIndex]
        $current = Join-Path $current $segment
        if (-not (Test-Path -LiteralPath $current)) { break }
        $item = Get-Item -LiteralPath $current -Force
        if ($segmentIndex -lt ($segments.Count - 1) -and -not $item.PSIsContainer) {
            throw "Unsafe non-directory component in project path: $current"
        }
        $isReparse = ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
        $linkType = if ($item.PSObject.Properties.Name -contains 'LinkType') { [string]$item.LinkType } else { '' }
        $targets = if ($item.PSObject.Properties.Name -contains 'Target') { @($item.Target | Where-Object { $_ }) } else { @() }
        $redirectsName = $linkType -in @('SymbolicLink', 'Junction', 'MountPoint') -or $targets.Count -gt 0
        if ($isReparse -and $redirectsName) {
            throw "Unsafe reparse-point component in project path: $current"
        }
    }
}

function Resolve-SafeProjectChild {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)][string]$Label
    )
    if ([string]::IsNullOrWhiteSpace($RelativePath) -or
        [System.IO.Path]::IsPathRooted($RelativePath) -or
        $RelativePath -match '^[A-Za-z]:' -or
        $RelativePath -match '(^|[\\/])\.\.([\\/]|$)') {
        throw "Unsafe project-configured $Label path: $RelativePath"
    }
    $candidate = Get-NormalizedFullPath -Path (Join-Path $Root $RelativePath)
    if (-not (Test-IsEqualOrDescendant -Candidate $candidate -Base $Root)) {
        throw "Unsafe project-configured $Label path: $RelativePath"
    }
    Assert-NoReparsePointInExistingPath -Path $candidate
    return $candidate
}

function Write-AtomicUtf8 {
    param(
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$Content,
        [switch]$AllowOverwrite
    )
    Assert-NoReparsePointInExistingPath -Path $Target
    if (Test-Path -LiteralPath $Target -PathType Container) {
        throw "Refusing to write a managed file over an existing directory: $Target"
    }
    $targetDirectory = Split-Path -Parent $Target
    if (-not (Test-Path -LiteralPath $targetDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    }
    $temporary = Join-Path $targetDirectory ('.' + [System.IO.Path]::GetFileName($Target) + '.' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [System.IO.File]::WriteAllText($temporary, $Content, [System.Text.UTF8Encoding]::new($false))
        if ($AllowOverwrite) {
            Move-Item -LiteralPath $temporary -Destination $Target -Force
        }
        else {
            # File.Move provides atomic create-only publication on the target
            # volume and cannot overwrite a file created after preflight.
            [System.IO.File]::Move($temporary, $Target)
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporary -PathType Leaf) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function Read-BoundedUtf8Text {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [System.IO.Stream]$InputStream,
        [scriptblock]$AfterLengthCheck
    )
    $ownsStream = $false
    if ($null -eq $InputStream) {
        $InputStream = [System.IO.FileStream]::new(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::Read
        )
        $ownsStream = $true
    }
    try {
        if (-not $InputStream.CanRead) {
            throw "Input stream is not readable: $Path"
        }
        if ([int64]$InputStream.Length -gt [int64]$MaxInitInputBytes) {
            throw "Input file exceeds the $MaxInitInputBytes-byte safe size limit: $Path"
        }
        if ($null -ne $AfterLengthCheck) {
            & $AfterLengthCheck
        }
        $buffer = [byte[]]::new([int]$MaxInitInputBytes + 1)
        $total = 0
        while ($total -lt $buffer.Length) {
            $read = $InputStream.Read($buffer, $total, $buffer.Length - $total)
            if ($read -eq 0) { break }
            $total += $read
        }
        if ($total -gt $MaxInitInputBytes) {
            throw "Input file exceeds the $MaxInitInputBytes-byte safe size limit: $Path"
        }
        $offset = 0
        if ($total -ge 3 -and $buffer[0] -eq 0xEF -and $buffer[1] -eq 0xBB -and $buffer[2] -eq 0xBF) {
            $offset = 3
        }
        $strictUtf8 = [System.Text.UTF8Encoding]::new($false, $true)
        return $strictUtf8.GetString($buffer, $offset, $total - $offset)
    }
    finally {
        if ($ownsStream) {
            $InputStream.Dispose()
        }
    }
}

function Read-JsonObjectSafe {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $value = (Read-BoundedUtf8Text -Path $Path | ConvertFrom-Json)
        if ($value -isnot [System.Management.Automation.PSCustomObject]) {
            throw "JSON root must be an object"
        }
        return $value
    }
    catch {
        throw "Refusing -Force because an existing managed JSON file is unreadable or is not an object: $Path ($($_.Exception.Message))"
    }
}

function Assert-NoApprovedProductionState {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [object]$Project
    )
    $requiredPathKeys = @(
        'story', 'storyboard', 'lookdev', 'assets', 'shots',
        'source_library', 'edit', 'delivery', 'approvals', 'schemas', 'logs'
    )
    $requiredAuthorityKeys = @(
        'story_contract', 'storyboard', 'visual_bible', 'asset_records_root',
        'asset_index', 'schema_manifest', 'source_manifest', 'timeline',
        'delivery_record'
    )
    $configuredPathRoots = @{}
    $configuredApprovals = '09_approvals'
    if ($null -ne $Project) {
        if ($Project -isnot [System.Management.Automation.PSCustomObject]) {
            throw "Unsafe existing project object"
        }
        if ($Project.PSObject.Properties.Name -notcontains 'paths' -or
            $null -eq $Project.paths -or
            $Project.paths -isnot [System.Management.Automation.PSCustomObject]) {
            throw "Unsafe project-configured paths map"
        }
        foreach ($requiredPathKey in $requiredPathKeys) {
            if ($Project.paths.PSObject.Properties.Name -notcontains $requiredPathKey -or
                $Project.paths.$requiredPathKey -isnot [string] -or
                [string]::IsNullOrWhiteSpace($Project.paths.$requiredPathKey)) {
                throw "Unsafe or missing project-configured path: $requiredPathKey"
            }
            $configuredPathRoots[$requiredPathKey] = Resolve-SafeProjectChild `
                -Root $Root `
                -RelativePath $Project.paths.$requiredPathKey `
                -Label ("path " + $requiredPathKey)
        }
        $configuredApprovals = $Project.paths.approvals
        if ($Project.PSObject.Properties.Name -notcontains 'authority_files' -or
            $null -eq $Project.authority_files -or
            $Project.authority_files -isnot [System.Management.Automation.PSCustomObject]) {
            throw "Unsafe project-configured authority map"
        }
        foreach ($requiredAuthorityKey in $requiredAuthorityKeys) {
            if ($Project.authority_files.PSObject.Properties.Name -notcontains $requiredAuthorityKey -or
                $Project.authority_files.$requiredAuthorityKey -isnot [string] -or
                [string]::IsNullOrWhiteSpace($Project.authority_files.$requiredAuthorityKey)) {
                throw "Unsafe or missing project-configured authority path: $requiredAuthorityKey"
            }
        }
    }
    $configuredApprovalRoot = if ($null -ne $Project) {
        $configuredPathRoots['approvals']
    }
    else {
        Resolve-SafeProjectChild -Root $Root -RelativePath $configuredApprovals -Label 'approvals'
    }
    $approvalRoots = @(
        $configuredApprovalRoot,
        (Join-Path $Root '01_story\approvals'),
        (Join-Path $Root '02_storyboard\approvals'),
        (Join-Path $Root '03_lookdev\approvals')
    ) | Select-Object -Unique
    foreach ($approvalRoot in $approvalRoots) {
        if (-not (Test-Path -LiteralPath $approvalRoot -PathType Container)) { continue }
        foreach ($approvalFile in @(Get-ChildItem -LiteralPath $approvalRoot -Filter '*.json' -File -Recurse -Force)) {
            if ($approvalFile.FullName -like '*\_templates\*') { continue }
            Assert-NoReparsePointInExistingPath -Path $approvalFile.FullName
            $approval = Read-JsonObjectSafe -Path $approvalFile.FullName
            if ($approval.review_status -notin @('DRAFT', 'LEGACY_UNVERIFIED')) {
                throw "Refusing -Force because a prepared, decided, or historical central approval exists: $($approvalFile.FullName)"
            }
        }
    }

    if ($null -ne $Project) {
        foreach ($authorityProperty in @($Project.authority_files.PSObject.Properties)) {
            if ($authorityProperty.Value -isnot [string] -or [string]::IsNullOrWhiteSpace($authorityProperty.Value)) {
                throw "Unsafe project-configured authority path for $($authorityProperty.Name)"
            }
            $authorityTarget = Resolve-SafeProjectChild -Root $Root -RelativePath $authorityProperty.Value -Label ("authority " + $authorityProperty.Name)
            $authorityJsonFiles = @()
            if (Test-Path -LiteralPath $authorityTarget -PathType Container) {
                $authorityJsonFiles = @(Get-ChildItem -LiteralPath $authorityTarget -Filter '*.json' -File -Recurse -Force)
            }
            elseif ((Test-Path -LiteralPath $authorityTarget -PathType Leaf) -and [System.IO.Path]::GetExtension($authorityTarget) -eq '.json') {
                $authorityJsonFiles = @(Get-Item -LiteralPath $authorityTarget -Force)
            }
            foreach ($authorityFile in $authorityJsonFiles) {
                Assert-NoReparsePointInExistingPath -Path $authorityFile.FullName
                $authorityRecord = Read-JsonObjectSafe -Path $authorityFile.FullName
                $legacyStatusProperty = $authorityRecord.PSObject.Properties['review_status']
                if ($null -ne $legacyStatusProperty -and $legacyStatusProperty.Value -notin @('DRAFT', 'LEGACY_UNVERIFIED')) {
                    throw "Refusing -Force because a configured authority carries protected review state: $($authorityFile.FullName)"
                }
                if ($authorityRecord.lock_status -in @('SOURCE_LOCKED', 'PICTURE_LOCKED')) {
                    throw "Refusing -Force because a configured authority is locked: $($authorityFile.FullName)"
                }
            }
        }
    }

    $managedPatterns = if ($null -ne $Project) {
        @(
            (Join-Path $configuredPathRoots['storyboard'] 'storyboard.json'),
            (Join-Path $configuredPathRoots['assets'] 'records\*\asset.json'),
            (Join-Path $configuredPathRoots['shots'] '*\shot.json'),
            (Join-Path $configuredPathRoots['shots'] '*\takes\*\take.json'),
            (Join-Path $configuredPathRoots['source_library'] 'source_manifest.json'),
            (Join-Path $configuredPathRoots['edit'] 'timeline.json'),
            (Join-Path $configuredPathRoots['edit'] 'records\*\v*\timeline.json'),
            (Join-Path $configuredPathRoots['delivery'] 'delivery.json'),
            (Join-Path $configuredPathRoots['delivery'] 'records\*\v*\delivery.json')
        )
    }
    else {
        @(
            (Join-Path $Root '02_storyboard\storyboard.json'),
            (Join-Path $Root '04_assets\records\*\asset.json'),
            (Join-Path $Root '05_shots\*\shot.json'),
            (Join-Path $Root '05_shots\*\takes\*\take.json'),
            (Join-Path $Root '06_source_library\source_manifest.json'),
            (Join-Path $Root '07_edit\timeline.json'),
            (Join-Path $Root '07_edit\records\*\v*\timeline.json'),
            (Join-Path $Root '08_delivery\delivery.json'),
            (Join-Path $Root '08_delivery\records\*\v*\delivery.json')
        )
    }
    foreach ($pattern in $managedPatterns) {
        foreach ($managedFile in @(Get-ChildItem -Path $pattern -File -Force -ErrorAction SilentlyContinue)) {
            Assert-NoReparsePointInExistingPath -Path $managedFile.FullName
            $record = Read-JsonObjectSafe -Path $managedFile.FullName
            $legacyStatusProperty = $record.PSObject.Properties['review_status']
            if ($null -ne $legacyStatusProperty -and $legacyStatusProperty.Value -notin @('DRAFT', 'LEGACY_UNVERIFIED')) {
                throw "Refusing -Force because a legacy managed artifact carries protected review state: $($managedFile.FullName)"
            }
            if ($record.lock_status -in @('SOURCE_LOCKED', 'PICTURE_LOCKED')) {
                throw "Refusing -Force because a managed authority is locked: $($managedFile.FullName)"
            }
        }
    }
}

$resolvedProjectRoot = Get-NormalizedFullPath -Path $ProjectRoot
$resolvedTemplateRoot = Get-NormalizedFullPath -Path $TemplateRoot
$skillRoot = Get-NormalizedFullPath -Path (Join-Path $runtimeScriptRoot '..')
$schemaRoot = Get-NormalizedFullPath -Path (Join-Path $skillRoot 'schemas')
$filesystemRoot = [System.IO.Path]::GetPathRoot($resolvedProjectRoot).TrimEnd('\', '/')
$userProfile = if ($env:USERPROFILE) { Get-NormalizedFullPath -Path $env:USERPROFILE } else { $null }

Assert-NoReparsePointInExistingPath -Path $resolvedProjectRoot

$protectedRoots = @($skillRoot, $resolvedTemplateRoot, $schemaRoot)
if ($env:SystemRoot) { $protectedRoots += (Get-NormalizedFullPath -Path $env:SystemRoot) }
if ($env:ProgramFiles) { $protectedRoots += (Get-NormalizedFullPath -Path $env:ProgramFiles) }
if (${env:ProgramFiles(x86)}) { $protectedRoots += (Get-NormalizedFullPath -Path ${env:ProgramFiles(x86)}) }
$protectedConflict = $false
foreach ($protectedRoot in $protectedRoots) {
    if ((Test-IsEqualOrDescendant -Candidate $resolvedProjectRoot -Base $protectedRoot) -or
        (Test-IsEqualOrDescendant -Candidate $protectedRoot -Base $resolvedProjectRoot)) {
        $protectedConflict = $true
        break
    }
}
if ($resolvedProjectRoot -eq $filesystemRoot -or ($userProfile -and $resolvedProjectRoot -eq $userProfile) -or $protectedConflict) {
    throw "Unsafe project root: $resolvedProjectRoot"
}
if (-not (Test-Path -LiteralPath $resolvedTemplateRoot -PathType Container)) {
    throw "Template directory not found: $resolvedTemplateRoot"
}
if (-not (Test-Path -LiteralPath $schemaRoot -PathType Container)) {
    throw "Schema directory not found: $schemaRoot"
}

if ($Force) {
    $existingProjectFile = Join-Path $resolvedProjectRoot 'project.json'
    if (Test-Path -LiteralPath $existingProjectFile -PathType Leaf) {
        $existingProject = Read-JsonObjectSafe -Path $existingProjectFile
        if ($existingProject -isnot [System.Management.Automation.PSCustomObject]) {
            throw 'Refusing -Force because existing project.json is not an object'
        }
        $approvedGate = @($existingProject.stage_gates.PSObject.Properties | Where-Object { $_.Value -eq 'USER_APPROVED' }).Count -gt 0
        $activeApprovals = @($existingProject.active_approval_ids).Count -gt 0
        if ($approvedGate -or $activeApprovals) {
            throw 'Refusing -Force reinitialization of a project with approved gates or active approvals'
        }
    }
    Assert-NoApprovedProductionState -Root $resolvedProjectRoot -Project $existingProject
}

$directories = @(
    '00_schemas',
    '01_story',
    '01_story\history\story-contract',
    '02_storyboard',
    '02_storyboard\panels',
    '02_storyboard\history',
    '03_lookdev',
    '03_lookdev\concept_frames',
    '03_lookdev\history\visual-bible',
    '04_assets\records',
    '04_assets\_templates',
    '05_shots\_templates',
    '06_source_library\approved_video',
    '06_source_library\approved_audio',
    '06_source_library\history',
    '07_edit\proxies',
    '07_edit\previews',
    '07_edit\records',
    '08_delivery\masters',
    '08_delivery\records',
    '09_approvals\_templates',
    '99_logs'
)

$fileMap = @(
    @{ Source = 'project.json'; Target = 'project.json'; Json = $true; Schema = 'project.schema.json' },
    @{ Source = 'STORY_CONTRACT.md'; Target = '01_story\STORY_CONTRACT.md'; Json = $false },
    @{ Source = 'storyboard.json'; Target = '02_storyboard\storyboard.json'; Json = $true; Schema = 'storyboard.schema.json' },
    @{ Source = 'VISUAL_BIBLE.md'; Target = '03_lookdev\VISUAL_BIBLE.md'; Json = $false },
    @{ Source = 'ASSET_INDEX.json'; Target = '04_assets\asset-index.json'; Json = $true },
    @{ Source = 'ASSET_RECORD.json'; Target = '04_assets\_templates\ASSET_RECORD.json'; Json = $true; Schema = 'asset.schema.json' },
    @{ Source = 'CHARACTER_PROFILE.yaml'; Target = '04_assets\_templates\CHARACTER_PROFILE.yaml'; Json = $false },
    @{ Source = 'LOCATION_MAP.yaml'; Target = '04_assets\_templates\LOCATION_MAP.yaml'; Json = $false },
    @{ Source = 'SOURCE_MANIFEST.json'; Target = '06_source_library\source_manifest.json'; Json = $true; Schema = 'source-library.schema.json' },
    @{ Source = 'TIMELINE.json'; Target = '07_edit\timeline.json'; Json = $true; Schema = 'timeline.schema.json' },
    @{ Source = 'DELIVERY_RECORD.json'; Target = '08_delivery\delivery.json'; Json = $true; Schema = 'delivery.schema.json' },
    @{ Source = 'SHOT_CARD.json'; Target = '05_shots\_templates\SHOT_CARD.json'; Json = $true; Schema = 'shot.schema.json' },
    @{ Source = 'TAKE_RECORD.json'; Target = '05_shots\_templates\TAKE_RECORD.json'; Json = $true; Schema = 'take.schema.json' },
    @{ Source = 'APPROVAL.json'; Target = '09_approvals\_templates\APPROVAL.json'; Json = $true; Schema = 'approval.schema.json' },
    @{ Source = 'REVIEW_REPORT.md'; Target = '99_logs\REVIEW_REPORT_TEMPLATE.md'; Json = $false }
)

$schemaFiles = @(Get-ChildItem -LiteralPath $schemaRoot -Filter '*.schema.json' -File | Sort-Object Name)
$schemaManifestSource = Join-Path $schemaRoot 'schema-manifest.json'
if (-not (Test-Path -LiteralPath $schemaManifestSource -PathType Leaf)) {
    throw "Trusted schema manifest missing: $schemaManifestSource"
}

$createdAt = [DateTimeOffset]::UtcNow.ToString('o')
$renderedFiles = @()
foreach ($relativeDirectory in $directories) {
    $directoryTarget = Join-Path $resolvedProjectRoot $relativeDirectory
    Assert-NoReparsePointInExistingPath -Path $directoryTarget
    if ((Test-Path -LiteralPath $directoryTarget) -and
        -not (Test-Path -LiteralPath $directoryTarget -PathType Container)) {
        throw "Refusing to create a managed directory over an existing file: $directoryTarget"
    }
}
foreach ($mapping in $fileMap) {
    $sourcePath = Join-Path $resolvedTemplateRoot $mapping.Source
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Required template missing: $sourcePath"
    }
    $targetPath = Join-Path $resolvedProjectRoot $mapping.Target
    Assert-NoReparsePointInExistingPath -Path $targetPath
    if (Test-Path -LiteralPath $targetPath -PathType Container) {
        throw "Refusing to write a managed file over an existing directory: $targetPath"
    }
    if ((Test-Path -LiteralPath $targetPath) -and -not $Force) {
        throw "Refusing to overwrite managed file without -Force: $targetPath"
    }
    $content = Read-BoundedUtf8Text -Path $sourcePath
    if ($mapping.Json) {
        $document = $content | ConvertFrom-Json
        if ($document.PSObject.Properties.Name -contains 'project_id') {
            $document.project_id = $ProjectId
        }
        if ($mapping.Source -eq 'project.json') {
            $document.project_prefix = $ProjectPrefix
            $document.title = $Title
            $document.notes = 'Initialized Cinema Studio project.'
            if ($document.PSObject.Properties.Name -contains 'created_at') {
                $document.created_at = $createdAt
            }
            else {
                $document | Add-Member -NotePropertyName 'created_at' -NotePropertyValue $createdAt
            }
        }
        if ($mapping.ContainsKey('Schema') -and ($document.PSObject.Properties.Name -contains '$schema')) {
            $targetParent = Split-Path -Parent $mapping.Target
            $depth = if ([string]::IsNullOrWhiteSpace($targetParent)) { 0 } else { @($targetParent -split '[\\/]' | Where-Object { $_ }).Count }
            $prefix = ''
            for ($index = 0; $index -lt $depth; $index++) { $prefix += '../' }
            $document.'$schema' = $prefix + '00_schemas/' + $mapping.Schema
        }
        $content = ($document | ConvertTo-Json -Depth 100) + "`n"
    }
    else {
        $content = $content.Replace('{{PROJECT_ID}}', $ProjectId).Replace('{{PROJECT_TITLE}}', $Title).Replace('{{PROJECT_PREFIX}}', $ProjectPrefix)
        if ($mapping.Source -in @('STORY_CONTRACT.md', 'VISUAL_BIBLE.md')) {
            $content = [regex]::Replace(
                $content,
                '(?m)^- Project ID: `[^`]+`$',
                ('- Project ID: `' + $ProjectId + '`')
            )
        }
    }
    $renderedFiles += [pscustomobject]@{ Target = $targetPath; Content = $content }
}
$renderedSchemas = @()
foreach ($schemaFile in $schemaFiles) {
    $targetPath = Join-Path $resolvedProjectRoot (Join-Path '00_schemas' $schemaFile.Name)
    Assert-NoReparsePointInExistingPath -Path $targetPath
    if (Test-Path -LiteralPath $targetPath -PathType Container) {
        throw "Refusing to write a managed schema over an existing directory: $targetPath"
    }
    if ((Test-Path -LiteralPath $targetPath) -and -not $Force) {
        throw "Refusing to overwrite managed schema without -Force: $targetPath"
    }
    $renderedSchemas += [pscustomobject]@{
        Target = $targetPath
        Content = Read-BoundedUtf8Text -Path $schemaFile.FullName
    }
}
$schemaManifestTarget = Join-Path $resolvedProjectRoot '00_schemas\schema-manifest.json'
Assert-NoReparsePointInExistingPath -Path $schemaManifestTarget
if (Test-Path -LiteralPath $schemaManifestTarget -PathType Container) {
    throw "Refusing to write the schema manifest over an existing directory: $schemaManifestTarget"
}
if ((Test-Path -LiteralPath $schemaManifestTarget) -and -not $Force) {
    throw "Refusing to overwrite managed schema manifest without -Force: $schemaManifestTarget"
}
$schemaManifestContent = Read-BoundedUtf8Text -Path $schemaManifestSource

if (-not $PSCmdlet.ShouldProcess($resolvedProjectRoot, "Initialize Cinema Studio project '$ProjectId'")) {
    return
}

New-Item -ItemType Directory -Path $resolvedProjectRoot -Force | Out-Null
foreach ($relativeDirectory in $directories) {
    $directoryTarget = Join-Path $resolvedProjectRoot $relativeDirectory
    Assert-NoReparsePointInExistingPath -Path $directoryTarget
    New-Item -ItemType Directory -Path $directoryTarget -Force | Out-Null
}

foreach ($schemaDocument in $renderedSchemas) {
    Write-AtomicUtf8 -Target $schemaDocument.Target -Content $schemaDocument.Content -AllowOverwrite:$Force
}
Write-AtomicUtf8 -Target $schemaManifestTarget -Content $schemaManifestContent -AllowOverwrite:$Force

foreach ($renderedFile in $renderedFiles) {
    Write-AtomicUtf8 -Target $renderedFile.Target -Content $renderedFile.Content -AllowOverwrite:$Force
}

[ordered]@{
    ok = $true
    project_root = $resolvedProjectRoot
    project_id = $ProjectId
    managed_files = $fileMap.Count + $schemaFiles.Count
    force = [bool]$Force
} | ConvertTo-Json -Depth 4
