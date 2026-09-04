# Build e distribuicao

## Pre-requisitos

- Windows 10 ou 11.
- Python 3.11 ou superior acessivel pelo comando `python`.
- Dependencias de `requirements.txt` instaladas.
- `ffmpeg.exe` e `ffprobe.exe` em `ferramentas\ffmpeg\bin\`.
- Icone em `assets\SeparadorVideo.ico`.

Instalacao do ambiente:

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALAR_WINDOWS.ps1
```

## Gerar o pacote

```powershell
powershell -ExecutionPolicy Bypass -File .\CRIAR_EXECUTAVEL.ps1
```

Para gerar apenas a pasta e pular a compactacao:

```powershell
powershell -ExecutionPolicy Bypass -File .\CRIAR_EXECUTAVEL.ps1 -SkipZip
```

Saidas locais:

```text
executaveis/
|-- SeparadorVideo/
|   |-- SeparadorVideo.exe
|   `-- _internal/
`-- SeparadorVideo_Windows.zip
```

O pacote e `onedir`: o `.exe` depende da pasta `_internal`. A distribuicao correta e o ZIP completo, nunca apenas o executavel isolado.

## Conteudo e decisoes do build

- FFmpeg e FFprobe sao incluidos no pacote.
- Assets e o icone sao incluidos.
- Faster-Whisper e CTranslate2 formam o backend de transcricao do executavel.
- Modelos nao sao incluidos; sao baixados na primeira utilizacao.
- PyTorch e OpenAI Whisper sao excluidos do pacote para evitar centenas de megabytes adicionais.
- Builds, ZIPs e modelos nao sao versionados no Git.

## Verificar o executavel

```powershell
& .\executaveis\SeparadorVideo\SeparadorVideo.exe --self-test
$LASTEXITCODE
```

O codigo de saida esperado e `0`. Para um teste completo de cinco segundos, use uma amostra local:

```powershell
& .\executaveis\SeparadorVideo\SeparadorVideo.exe --runtime-test "C:\amostras\video.mp4"
$LASTEXITCODE
```

Esse teste usa o perfil equilibrado e transcreve do segundo 2 ao 7. Ele pode baixar o modelo na primeira execucao.

Depois, extraia o ZIP em outro diretorio e abra o aplicativo. Isso detecta dependencias que funcionavam apenas por estarem presentes no repositorio.

## Integridade da release

```powershell
Get-FileHash .\executaveis\SeparadorVideo_Windows.zip -Algorithm SHA256
```

Publique o hash junto do arquivo na release do GitHub. Recalcule sempre que o ZIP for gerado novamente.
