# FEATURE: Portfolio_Foundry_v0.38.0.20.16309_BUILD49_TEST62
param(
  [switch]$OpenBrowser,
  [switch]$Smoke,
  [int]$Port = 8071
)
$ErrorActionPreference = 'Stop'
$FeatureToken = 'Portfolio_Foundry_v0.38.0.20.16309_BUILD49_TEST62'
$FeatureRevision = 'PATCH_READY1'
$FeatureLog = "feature_token=$FeatureToken feature_revision=$FeatureRevision"
$env:PORTFOLIO_FOUNDRY_FEATURE_TOKEN = $FeatureToken
$BuildToken = 'BUILD237_TEST250'
$FactoryVersion = 'v39.3.4492.96'
$env:PORTFOLIO_FOUNDRY_BUILD_TOKEN = $BuildToken
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
$env:PYTHONDONTWRITEBYTECODE = '1'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Requirements = Join-Path $Root 'requirements.txt'
$FoundryDir = Join-Path $Root 'foundry'
$RuntimeEnvironment = Join-Path $FoundryDir 'runtime-environment.json'

function Resolve-BootstrapPython {
  if ($env:PORTFOLIO_FOUNDRY_PYTHON) { return $env:PORTFOLIO_FOUNDRY_PYTHON }
  foreach ($candidate in @('py -3','python','python3')) {
    try {
      $parts = $candidate -split ' '
      if (Get-Command $parts[0] -ErrorAction SilentlyContinue) { return $candidate }
    } catch {}
  }
  throw "[$BuildToken] Python 3 runtime not found. Install Python 3 or make py/python available in PATH."
}

function Invoke-Bootstrap([string]$Python, [string[]]$Arguments) {
  if ($Python -eq 'py -3') { & py -3 @Arguments }
  else { & $Python @Arguments }
}

function Get-Sha256Text([string]$Text) {
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $hash = $sha.ComputeHash($bytes)
    return ([BitConverter]::ToString($hash) -replace '-', '').ToLowerInvariant()
  } finally { $sha.Dispose() }
}

Write-Host "[$FeatureLog][v0.31][$BuildToken] Runtime Manager - resolve external runtime cache"
$BootstrapPython = Resolve-BootstrapPython
$PythonVersion = (Invoke-Bootstrap $BootstrapPython @('--version') 2>&1 | Out-String).Trim()
if (-not $PythonVersion) { throw "[$BuildToken] Python version probe failed." }
$RequirementsText = if (Test-Path $Requirements) { [IO.File]::ReadAllText($Requirements) } else { '' }
$RequirementsFingerprint = Get-Sha256Text $RequirementsText
$LocalAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
if (-not $LocalAppData) { throw "[$BuildToken] LocalApplicationData is unavailable." }
$Manager = Join-Path $PSScriptRoot 'runtime_manager.py'
if (-not (Test-Path $Manager)) { throw "[$BuildToken] Shared runtime manager is missing." }
$EnvironmentId = $null
$EnvironmentProbe = Join-Path $PSScriptRoot 'execution_environment.py'
if (Test-Path $EnvironmentProbe) {
  try {
    $Snapshot = (Invoke-Bootstrap $BootstrapPython @($EnvironmentProbe, '--snapshot', '--history-root', (Join-Path $LocalAppData 'PortfolioFoundry\cache\work-history'), '--build-version', $FactoryVersion, '--build-token', $BuildToken) | Out-String) | ConvertFrom-Json
    $EnvironmentId = $Snapshot.snapshotId
  } catch { Write-Host "[$FeatureLog] Hardware details unavailable; runtime preparation continues." }
}
$RequestPath = Join-Path ([IO.Path]::GetTempPath()) (([Guid]::NewGuid().ToString('N')) + '.runtime-request.json')
$Request = @{
  mode = 'ensure'
  cacheRoot = (Join-Path $LocalAppData 'PortfolioFoundry\cache')
  requirements = @($RequirementsText -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
  context = @{ runId = [Guid]::NewGuid().ToString('N'); stage = '9'; candidateId = (Split-Path $Root -Leaf); environmentId = $EnvironmentId }
}
try {
  $Request | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $RequestPath
  $script:RuntimeResult = $null
  Invoke-Bootstrap $BootstrapPython @($Manager, '--request', $RequestPath) | ForEach-Object {
    try {
      $Event = $_ | ConvertFrom-Json
      if ($Event.phase -eq 'result' -and $Event.status -eq 'PASS') { $script:RuntimeResult = $Event.result }
      if ($Event.message) { Write-Host "[$FeatureLog] $($Event.message)" }
      elseif ($Event.phase) { Write-Host ("[$FeatureLog][{0}] {1}" -f $Event.phase,$Event.status) }
    } catch { Write-Host "[$FeatureLog] $_" }
  }
  if (-not $script:RuntimeResult) { throw 'Shared runtime preparation failed; see the runtime library log.' }
  $VenvPython = $script:RuntimeResult.pythonPath
  $CacheKey = $script:RuntimeResult.runtimeId
  $RuntimeRelativePath = $script:RuntimeResult.relativePath
} finally { Remove-Item -ErrorAction SilentlyContinue $RequestPath }

New-Item -ItemType Directory -Force -Path $FoundryDir | Out-Null
$Descriptor = [ordered]@{
  schema = 'portfolio-foundry.runtime-environment.v2'
  featureToken = $FeatureToken
  featureRevision = $FeatureRevision
  profile = 'v031-python-runtime-v1'
  cache_key = $CacheKey
  runtime_relative_path = $RuntimeRelativePath
  requirements_fingerprint = $RequirementsFingerprint
  python_version = $PythonVersion
  status = 'READY'
  factory_version = $FactoryVersion
  build_token = $BuildToken
}
$Descriptor | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $RuntimeEnvironment

Write-Host "[$FeatureLog][v0.31][$BuildToken] preflight"
& $VenvPython -c "import json,sys; print(json.dumps({'featureToken':'$FeatureToken','featureRevision':'$FeatureRevision','python':sys.version.split()[0],'status':'READY','bytecode':sys.dont_write_bytecode}))"
if ($LASTEXITCODE -ne 0) { throw "[$BuildToken] Runtime preflight failed." }

if ($Smoke) {
  Write-Host "[$FeatureLog][v0.31][$BuildToken] runtime / UI smoke"
  & $VenvPython (Join-Path $Root 'scripts\runtime_smoke.py') --project-root $Root --python $VenvPython
  exit $LASTEXITCODE
}

$Url = "http://127.0.0.1:$Port/"
Write-Host "[$FeatureLog][v0.31][$BuildToken] start server · $Url"
$Server = Join-Path $Root 'src\app\server.py'
if ($OpenBrowser) {
  Start-Process powershell.exe -ArgumentList @('-NoProfile','-Command',"Start-Sleep -Milliseconds 900; Start-Process '$Url'") | Out-Null
}
& $VenvPython $Server --project-root $Root --port $Port
exit $LASTEXITCODE
