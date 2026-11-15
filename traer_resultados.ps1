<#
Trae a este PC la carpeta resultados/ de la placa por USB (adb).
  .\traer_resultados.ps1
#>
param(
  [string]$Origen = "/home/arduino/placa-velocidad/resultados",
  [string]$Adb = ""
)
$ErrorActionPreference = "Stop"
if (-not $Adb) {
  $c = Get-Command adb -ErrorAction SilentlyContinue
  $Adb = if ($c) { $c.Source } else { "D:\Datathon_A\herramientas\adb-platform-tools\platform-tools\adb.exe" }
}
if (-not (Test-Path $Adb)) { throw "No encuentro adb: pásalo con -Adb C:\ruta\adb.exe" }
& $Adb pull $Origen "$PSScriptRoot"
Get-ChildItem "$PSScriptRoot\resultados\*\resumen.md" | Sort-Object LastWriteTime | Select-Object -Last 1 | ForEach-Object {
  "Último resumen: $($_.FullName)"
  Get-Content $_.FullName -Encoding utf8
}
