param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $speaker.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'en-*' } | Select-Object -First 1
if (-not $voice) { throw 'Install a Windows English speech voice, or provide four local PCM WAV files.' }
$speaker.SelectVoice($voice.VoiceInfo.Name)
$speaker.Rate = 0
$lines = @('Make room for something better.', 'Meet the product made for your everyday life.', 'Thoughtful details bring comfort and confidence to every moment.', 'Choose Visora for your next move.')
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
try {
    for ($i=0; $i -lt 4; $i++) {
        $destination = Join-Path $OutputDirectory ('speech-raw-' + ($i + 1) + '.wav')
        $speaker.SetOutputToWaveFile($destination)
        $speaker.Speak($lines[$i])
        $speaker.SetOutputToNull()
    }
} finally { $speaker.Dispose() }
