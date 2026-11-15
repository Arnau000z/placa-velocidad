<#
Copia este repo a la placa por USB (adb), con el predict.py más reciente del equipo.
  .\subir_a_placa.ps1                                   # scripts + predict.py
  .\subir_a_placa.ps1 -Modelos D:\Datathon_A\modelos    # además los .gguf de la lista que haya en esa carpeta
  .\subir_a_placa.ps1 -Extra D:\ruta\afinado.gguf       # además un modelo propio (luego: EXTRA=~/models/afinado.gguf)
Si la placa tiene buena wifi no hace falta -Modelos: 00_preparar.sh los baja solo.
#>
param(
  [string]$Destino = "/home/arduino/placa-velocidad",
  [string]$Modelos = "",
  [string[]]$Extra = @(),
  [string]$Predict = "D:\Datathon_A\entrega\predict.py",
  [string]$Adb = ""
)
$ErrorActionPreference = "Stop"

if (-not $Adb) {
  $c = Get-Command adb -ErrorAction SilentlyContinue
  if ($c) { $Adb = $c.Source }
  else {
    $dir = "D:\Datathon_A\herramientas\adb-platform-tools"
    $zip = "$dir\platform-tools-latest-windows.zip"
    if (-not (Test-Path "$dir\platform-tools\adb.exe") -and (Test-Path $zip)) { Expand-Archive $zip -DestinationPath $dir }
    $Adb = "$dir\platform-tools\adb.exe"
  }
}
if (-not (Test-Path $Adb)) { throw "No encuentro adb: pásalo con -Adb C:\ruta\adb.exe" }
$placas = & $Adb devices | Select-Object -Skip 1 | Where-Object { $_ -match "\tdevice$" }
if (-not $placas) { throw "No veo la placa por USB ('adb devices' no lista ninguna)" }

if (Test-Path $Predict) {
  Copy-Item $Predict "$PSScriptRoot\equipo\predict.py" -Force
  "predict.py actualizado desde $Predict"
}

& $Adb shell "mkdir -p $Destino/equipo"
Get-ChildItem $PSScriptRoot -File | Where-Object { $_.Extension -in ".sh", ".py", ".md" } | ForEach-Object {
  & $Adb push $_.FullName "$Destino/" | Out-Null
}
& $Adb push "$PSScriptRoot\equipo\predict.py" "$Destino/equipo/" | Out-Null
# Quitar finales CRLF por si el repo se clonó en Windows sin .gitattributes, y dar permisos
& $Adb shell ("sed -i 's/\r`$//' $Destino/*.sh $Destino/*.py $Destino/equipo/*.py && chmod +x $Destino/*.sh $Destino/*.py")
"Scripts en la placa: $Destino"

function Subir-Modelo([string]$ruta) {
  $nombre = Split-Path $ruta -Leaf
  $tam = (Get-Item $ruta).Length
  $remoto = (& $Adb shell "stat -c %s /home/arduino/models/$nombre 2>/dev/null").Trim()
  if ($remoto -eq "$tam") { "  ya está $nombre"; return }
  "  subiendo $nombre ($([math]::Round($tam / 1MB)) MB)..."
  & $Adb shell "mkdir -p /home/arduino/models"
  & $Adb push $ruta "/home/arduino/models/$nombre"
}

if ($Modelos) {
  $lista = Select-String -Path "$PSScriptRoot\config.sh" -Pattern '\[(.+\.gguf)\]=' | ForEach-Object { $_.Matches[0].Groups[1].Value }
  foreach ($n in $lista) {
    $r = Join-Path $Modelos $n
    if (Test-Path $r) { Subir-Modelo $r }
  }
}
foreach ($e in $Extra) { Subir-Modelo $e }

""
"En la placa:  cd $Destino && ./todo.sh        (o ./todo.sh rapido)"
