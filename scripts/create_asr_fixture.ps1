# Synthetic speech solely for local ASR validation; does not clone a person's voice.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speechFixtureRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'data/meetings/test-fixtures'
New-Item -ItemType Directory -Path $speechFixtureRoot -Force | Out-Null
$speechSynth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $portugueseVoice = $speechSynth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'pt-*' } | Select-Object -First 1
    if (-not $portugueseVoice) { throw 'Nenhuma voz portuguesa instalada para a fixture sintética.' }
    $speechSynth.SelectVoice($portugueseVoice.VoiceInfo.Name)
    $speechSynth.SetOutputToWaveFile((Join-Path $speechFixtureRoot 'compromisso-sintetico.wav'))
    # ASCII source plus XML entities also works in Windows PowerShell 5 (UTF-8 without BOM).
    $speechSynth.SpeakSsml('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="pt-BR">Eu vou consultar o diretor sobre a integra&#231;&#227;o. Posso enviar a documenta&#231;&#227;o amanh&#227;. A reuni&#227;o ser&#225; &#224;s duas. Corrigindo, a reuni&#227;o ser&#225; &#224;s tr&#234;s. Precisamos confirmar a data completa e o respons&#225;vel interno.</speak>')
    Write-Output ('Fixture sintética criada; voz: ' + $portugueseVoice.VoiceInfo.Name)
} finally {
    $speechSynth.Dispose()
}
