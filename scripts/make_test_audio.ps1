# Synthetic data only; uses locally installed Windows TTS voices, no cloud API.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
Add-Type -AssemblyName System.Speech
New-Item -ItemType Directory -Force data | Out-Null
$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $synth.SelectVoice('Microsoft Irina Desktop')
    $synth.SetOutputToWaveFile((Join-Path (Get-Location) 'data/synthetic-meeting.wav'))
    $synth.Speak('Сегодня обсуждаем подготовку отчёта. Айдана, подготовь финансовый отчёт до двадцать пятого сентября две тысячи двадцать шестого года. Тимур, проверь договор до тридцатого сентября. Следующее совещание состоится в пятницу.')
} finally { $synth.Dispose() }
Write-Output 'Created data/synthetic-meeting.wav. One synthetic speaker; not a diarization benchmark.'

$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $synth.SetOutputToWaveFile((Join-Path (Get-Location) 'data/two-speakers.wav'))
    $synth.SelectVoice('Microsoft Irina Desktop')
    $synth.Speak('Коллеги, начинаем совещание. Тимур, подготовь договор до тридцатого сентября две тысячи двадцать шестого года.')
    $synth.SelectVoice('Microsoft Pavel')
    $synth.Speak('Хорошо, подготовлю договор. Айдана, пришли финансовый отчёт до двадцать пятого сентября две тысячи двадцать шестого года.')
    $synth.SelectVoice('Microsoft Irina Desktop')
    $synth.Speak('Я пришлю отчёт в указанный срок. Спасибо, совещание закончено.')
} finally { $synth.Dispose() }
Write-Output 'Created data/two-speakers.wav. Two synthetic voices; real meeting accuracy is not measured.'
