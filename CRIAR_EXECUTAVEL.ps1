param([switch]$SkipZip)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$ffmpeg = Join-Path $PSScriptRoot "ferramentas\ffmpeg\bin\ffmpeg.exe"
$ffprobe = Join-Path $PSScriptRoot "ferramentas\ffmpeg\bin\ffprobe.exe"
$assets = Join-Path $PSScriptRoot "assets"
$icon = Join-Path $assets "SeparadorVideo.ico"
$entrypoint = Join-Path $PSScriptRoot "app\video_splitter_gui.py"
$dist = Join-Path $PSScriptRoot "executaveis"
$work = Join-Path $PSScriptRoot "ferramentas\build_novo"
if (-not (Test-Path -LiteralPath $ffmpeg) -or -not (Test-Path -LiteralPath $ffprobe)) {
    throw "FFmpeg nao encontrado em ferramentas\ffmpeg\bin."
}

$arguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--onedir",
    "--windowed",
    "--name", "SeparadorVideo",
    "--distpath", $dist,
    "--workpath", $work,
    "--specpath", $work,
    "--paths", $PSScriptRoot,
    "--icon", $icon,
    "--add-data", "$assets;assets",
    "--add-binary", "$ffmpeg;ffmpeg\bin",
    "--add-binary", "$ffprobe;ffmpeg\bin",
    "--hidden-import", "ctranslate2",
    "--hidden-import", "faster_whisper",
    "--collect-binaries", "ctranslate2",
    "--collect-data", "faster_whisper",
    "--collect-all", "charset_normalizer",
    "--collect-all", "chardet",
    "--exclude-module", "torch",
    "--exclude-module", "torchaudio",
    "--exclude-module", "torchvision",
    "--exclude-module", "whisper",
    "--exclude-module", "numba",
    "--exclude-module", "llvmlite",
    "--exclude-module", "transformers",
    "--exclude-module", "optimum",
    "--exclude-module", "accelerate",
    "--exclude-module", "pandas",
    "--exclude-module", "pyarrow",
    "--exclude-module", "sklearn",
    "--exclude-module", "scipy",
    "--exclude-module", "matplotlib",
    "--exclude-module", "IPython",
    "--exclude-module", "pytest",
    "--exclude-module", "tensorflow",
    "--exclude-module", "sqlalchemy",
    "--exclude-module", "uvicorn",
    "--exclude-module", "fsspec",
    "--exclude-module", "openpyxl",
    "--exclude-module", "jinja2",
    "--exclude-module", "PIL",
    "--exclude-module", "jax",
    "--exclude-module", "jaxlib",
    "--exclude-module", "polars",
    "--exclude-module", "tensorstore",
    "--exclude-module", "ml_dtypes",
    $entrypoint
)

python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao gerar o executavel."
}

$zipPath = Join-Path $dist "SeparadorVideo_Windows.zip"
if (-not $SkipZip) {
    Compress-Archive -Path (Join-Path $dist "SeparadorVideo\*") -DestinationPath $zipPath -Force
}

Write-Host "Executavel pronto: .\executaveis\SeparadorVideo\SeparadorVideo.exe"
if (-not $SkipZip) {
    Write-Host "Pacote para distribuir: $zipPath"
}
