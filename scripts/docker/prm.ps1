param(
    [Parameter(Position=0)]
    [ValidateSet('build','init','up','down','restart','logs','ps','workers','test','health','backup')]
    [string]$Action = 'ps',
    [string]$Service = '',
    [switch]$Dev,
    [ValidatePattern('^[a-z0-9][a-z0-9_-]*$')][string]$Project = 'prm-docker'
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $projectRoot
try {
    $composeArgs = @('compose', '-p', $Project, '-f', 'compose.yaml')
    if ($Dev) { $composeArgs += @('-f', 'compose.dev.yaml') }
    function Invoke-Compose {
        & docker @composeArgs @args
        if ($LASTEXITCODE -ne 0) { throw "Docker Compose falhou (exit $LASTEXITCODE)." }
    }
    switch ($Action) {
        'build' { Invoke-Compose build api }
        'init' {
            # Guard in docker/migrate.py refuses Windows/production databases.
            Invoke-Compose up -d --wait db
            Invoke-Compose run --rm migrate
        }
        'up' {
            if (!(Test-Path 'scripts/store_removal_worker.py')) {
                throw 'Worker de remoção ainda não versionado. Integre o PR funcional; use compose up api para validar somente a API.'
            }
            Invoke-Compose --profile workers up -d --wait
        }
        'down' { Invoke-Compose --profile workers down } # Never -v: preserve all volumes.
        'restart' { Invoke-Compose --profile workers restart }
        'logs' {
            if ($Service) { Invoke-Compose logs --tail 100 -f $Service }
            else { Invoke-Compose logs --tail 100 -f }
        }
        'ps' { Invoke-Compose --profile workers ps -a }
        'workers' { Invoke-Compose --profile workers ps -a }
        'test' {
            # No env_file, network, or real queues. Never compose run api pytest.
            & docker run --rm --network none prm:local python -m pytest -q
            if ($LASTEXITCODE -ne 0) { throw 'Testes falharam.' }
        }
        'health' {
            Invoke-Compose exec -T api python -c "import urllib.request; [print(p, urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/'+p, timeout=5).status) for p in ('live','ready')]"
        }
        'backup' {
            # Stop writers first; backup persists inside the isolated backups volume.
            Invoke-Compose --profile workers stop gateway api worker-registration worker-removal worker-datasheets worker-alerts
            Invoke-Compose run --rm --no-deps api python docker/backup.py
            Write-Host 'Backup concluído no volume backups. Serviços continuam parados; use up após conferir.'
        }
    }
} finally { Pop-Location }
