$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python nao foi encontrado. Instale o Python 3.11 ou superior e marque a opcao 'Add python.exe to PATH'."
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Write-Host ""
Write-Host "Dependencias instaladas."
Write-Host "Para abrir o app: clique duas vezes em SeparadorVideo.pyw"
Write-Host ""
Write-Host "Se o FFmpeg nao estiver instalado, instale com:"
Write-Host "winget install Gyan.FFmpeg"
