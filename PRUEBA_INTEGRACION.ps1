# Verificacion automatizada REAL en Windows:
# Mosquitto -> Edge SOS -> MQTT oficial -> Cloud SQLite -> HTTP -> reinicio -> SQLite.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$compose = @('-f','docker-compose.yml','-f','docker-compose.edge.yml','-f','docker-compose.cloud.yml')
$base = 'http://localhost:8090'

function Check-DockerExit($step) {
    if ($LASTEXITCODE -ne 0) { throw "${step}: docker terminó con código $LASTEXITCODE" }
}
function Wait-Cloud {
    for ($i=0; $i -lt 40; $i++) {
        try {
            $health = Invoke-RestMethod "$base/api/health" -TimeoutSec 2
            if ($health.mqtt_connected -eq $true) { return }
        } catch { }
        Start-Sleep -Milliseconds 750
    }
    throw 'La API no respondió con MQTT conectado. Revisar: docker compose ... logs cloud'
}

Write-Host '[1/5] Iniciando broker, Edge y servicio central...' -ForegroundColor Cyan
& docker compose @compose up -d --build mosquitto edge cloud
Check-DockerExit 'Arranque'
Wait-Cloud

Write-Host '[2/5] Comprobando que Edge está suscrito...' -ForegroundColor Cyan
$ready = $false
for ($i=0; $i -lt 20; $i++) {
    $logs = (& docker compose @compose logs --tail 80 edge 2>&1 | Out-String)
    if ($logs -match 'Edge conectado a Mosquitto') { $ready = $true; break }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) { throw 'Edge no muestra conexión MQTT. Revisar logs edge.' }

Write-Host '[3/5] Publicando un SOS único y buscando la alarma en SQLite...' -ForegroundColor Cyan
$testId = "SOS_DEMO_$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$payload = @{ node_id = $testId; zone = 'integracion_cloud_local' } | ConvertTo-Json -Compress
$payload | & docker compose @compose exec -T mosquitto mosquitto_pub -h localhost -t 'wildfiresense/events/sos' -s -q 1
Check-DockerExit 'Publicación SOS'

$found = $false
for ($i=0; $i -lt 30; $i++) {
    try {
        $result = Invoke-RestMethod "$base/api/alerts?node_id=$testId" -TimeoutSec 2
        if (@($result.alerts).Count -eq 1 -and $result.alerts[0].alert_type -eq 'sos_alert') {
            $found = $true
            break
        }
    } catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $found) { throw "SOS $testId no llegó a la base de datos; comprobar logs de Edge y cloud." }
Write-Host "  OK: SOS guardado con node_id=$testId" -ForegroundColor Green

Write-Host '[4/5] Reiniciando SOLO el receptor central para verificar persistencia...' -ForegroundColor Cyan
& docker compose @compose restart cloud
Check-DockerExit 'Reinicio cloud'
Wait-Cloud
$restored = Invoke-RestMethod "$base/api/alerts?node_id=$testId"
if (@($restored.alerts).Count -ne 1) { throw "La alarma $testId no sobrevivió al reinicio de cloud." }

Write-Host '[5/5] Verificación completada' -ForegroundColor Green
$stats = Invoke-RestMethod "$base/api/stats"
[pscustomobject]@{
    Resultado = 'OK - MQTT -> Edge -> SQLite -> HTTP -> reinicio'
    SOS_prueba = $testId
    Alarmas_almacenadas = $stats.total_alerts
    SOS_almacenados = $stats.sos_alerts
    Base_de_datos = 'cloud/data/alerts.sqlite3'
    Dashboard = $base
} | Format-List
