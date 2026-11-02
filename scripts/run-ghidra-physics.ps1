param([ValidateSet('physics','contacts','vehicle','world','controls','inputsource','wheelpipeline','sceneinputs')][string]$ResearchSet='physics')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$installation=Get-Content (Join-Path $root 'tools\ghidra-install.json') -Raw | ConvertFrom-Json
$ghidra=@($installation.packages | Where-Object name -eq 'Ghidra')[0].root
$env:JAVA_HOME=@($installation.packages | Where-Object name -eq 'Temurin JDK')[0].root
$env:PATH=(Join-Path $env:JAVA_HOME 'bin')+';'+$env:PATH
$homePath=(Join-Path $root 'cache\ghidra-home').Replace('\','/')
$tempPath=(Join-Path $root 'cache\temp').Replace('\','/')
$env:JAVA_TOOL_OPTIONS="-Duser.home=$homePath -Djava.io.tmpdir=$tempPath"
$env:GHIDRA_HEADLESS_MAXMEM='6G'
$projects=Join-Path $root 'local\recon\ghidra-projects'
New-Item -ItemType Directory -Force $homePath,$tempPath,$projects | Out-Null
& python (Join-Path $PSScriptRoot 'prepare_ghidra_physics.py') --set $ResearchSet
if($LASTEXITCODE -ne 0){throw 'Ghidra manifest preparation failed'}
$project='physics-2026-2-2'
$commandArgs=@($projects,$project)
if(Test-Path -LiteralPath (Join-Path $projects "$project.gpr")){$commandArgs+=@('-process','Trackmania.exe')}
else{$commandArgs+=@('-import','D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')}
$researchFolder=if($ResearchSet -eq 'physics'){'local\recon\ghidra'}else{'local\recon\ghidra-'+$ResearchSet}
$output=Join-Path $root ($researchFolder+'\decompiled')
$commandArgs+=@('-noanalysis','-max-cpu','4','-scriptPath',(Join-Path $PSScriptRoot 'ghidra'),'-postScript','TM2020Physics.java',(Join-Path $root ($researchFolder+'\physics-functions.tsv')),$output)
$log=Join-Path $root ('local\ghidra-headless-'+$ResearchSet+'-current.log')
& (Join-Path $ghidra 'support\analyzeHeadless.bat') @commandArgs *> $log
if($LASTEXITCODE -ne 0){throw "Ghidra launcher failed; see $log"}
if(!(Select-String -LiteralPath $log -Pattern 'PASS TM2020_GHIDRA selected=' -Quiet)){throw "Ghidra script did not finish; launcher exit status alone is insufficient. See $log"}
$report=Import-Csv (Join-Path $output 'decompile-report.tsv') -Delimiter "`t"
$manifest=Get-Content (Join-Path $root ($researchFolder+'\manifest.json')) -Raw | ConvertFrom-Json
$complete=@($report | Where-Object completed -eq 'true')
if($report.Count -ne $manifest.functions -or $complete.Count -ne $report.Count){throw 'One or more selected functions failed decompilation; inspect retained report'}
Write-Output "PASS GHIDRA_PHYSICS functions=$($complete.Count) pinned_original=true static_only=true"
