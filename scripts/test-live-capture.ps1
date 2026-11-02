$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$bin=Join-Path $root 'native\build\tm2020_capture.exe'
$dest=Join-Path $root 'local\telemetry\synthetic-test.ndjson'
New-Item -ItemType Directory -Force (Split-Path $dest -Parent)|Out-Null
Remove-Item $dest -Force -ErrorAction SilentlyContinue
if(-not (Test-Path $bin)){throw 'Compile tm2020_capture first'}
$port=24826
$argPath='"'+$dest+'"'
$p=Start-Process -FilePath $bin -ArgumentList @($argPath,"$port","16") -PassThru -WindowStyle Hidden
$tcp=$null
try {
  Start-Sleep -Milliseconds 350
  $tcp=[Net.Sockets.TcpClient]::new()
  $tcp.Connect('127.0.0.1',$port)
  $stream=$tcp.GetStream()
  $encoding=[Text.Encoding]::UTF8
  foreach($index in 0..15) {
     $row=[ordered]@{
       schema='tm2020_live_telemetry_v1'
       mapUid='synthetic-only-map-uid'
       raceStartMs=600
       simulationTimeCoef=1.0
       sequence=$index
       wallMs=1000+($index*10)
       frameDt=0.01
       position=@(1.0,2.0,3.0)
       velocity=@(0.5,0.0,25.0)
       dir=@(0.0,0.0,1.0)
       frontSpeed=25.0;sideSpeed=0.0;steer=0.0;gas=1.0;brake=0.0
       flSlip=0.0;frSlip=0.0;rlSlip=0.0;rrSlip=0.0
     }
     $bytes=$encoding.GetBytes(($row|ConvertTo-Json -Compress -Depth 5)+[Environment]::NewLine)
     $stream.Write($bytes,0,$bytes.Length)
  }
  $stream.Flush()
  $tcp.Close()
  $p.WaitForExit(7000)|Out-Null
  if(-not $p.HasExited){throw 'Timed out waiting for test collector'}
  if($p.ExitCode -ne 0){throw "Collector error exit=$($p.ExitCode)"}
  $lines=@(Get-Content $dest)
  if($lines.Count -ne 16){throw "Wrong records $($lines.Count) != 16"}
  $env:PYTHONDONTWRITEBYTECODE='1'
  & python (Join-Path $PSScriptRoot 'validate_live_capture.py') $dest --output (Join-Path $root 'local\telemetry\synthetic-test-validation.json')
  if($LASTEXITCODE -ne 0){throw 'Telemetry validator failed'}
  $report=Get-Content (Join-Path $root 'local\telemetry\synthetic-test-validation.json') -Raw|ConvertFrom-Json
  if(-not $report.metadataPresent -or $report.mapUids.Count -ne 1 -or $report.mapUids[0] -ne 'synthetic-only-map-uid'){
    throw 'Telemetry map UID metadata did not survive capture'
  }
  Write-Output 'PASS 16/16 fake frames: native collector + offline validator + map UID metadata'
}finally{
  if($null -ne $tcp){try{$tcp.Dispose()}catch{}}
  if(-not $p.HasExited){Stop-Process -Id $p.Id -Force}
}
