# Separador e Transcritor de Video

Aplicativo para Windows que divide videos em partes iguais e gera transcricoes em texto, legenda SRT, VTT e JSON.

## O que ele faz

- Divide videos em 2, 3 ou 4 partes.
- Comprime os videos usando FFmpeg.
- Usa aceleração NVIDIA NVENC quando disponível.
- Transcreve audio/video em português.
- Gera arquivos `.txt`, `.srt`, `.vtt` e `.json`.
- Organiza tudo dentro da pasta `saidas/`.

## Requisitos

- Windows 10 ou 11.
- Python 3.11 ou superior.
- FFmpeg instalado.
- Internet na primeira transcricao, para baixar o modelo Whisper.

## Instalacao

Baixe o projeto pelo GitHub e extraia a pasta.

Abra o PowerShell dentro da pasta do projeto e rode:

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALAR_WINDOWS.ps1
```

Se o FFmpeg ainda nao estiver instalado, rode:

```powershell
winget install Gyan.FFmpeg
```

Feche e abra o PowerShell depois da instalacao do FFmpeg.

## Como abrir

Clique duas vezes em:

```text
SeparadorVideo.pyw
```

Ele abre como aplicativo normal, sem terminal.

Se nao abrir, veja o arquivo:

```text
SeparadorVideo_erro.log
```

## Como usar

1. Clique em `Escolher video`.
2. Selecione o arquivo `.mp4`, `.mov`, `.mkv`, `.avi`, `.m4v` ou `.webm`.
3. Escolha a pasta de saida, se quiser mudar.
4. Para dividir o video, escolha 2, 3 ou 4 partes e clique em `Processar video`.
5. Para transcrever, escolha o perfil e o idioma e clique em `Transcrever video`.

As saidas ficam organizadas assim:

```text
saidas/
  nome-do-video/
    3_partes/
      nome-do-video_parte_01_de_03.mp4
      nome-do-video_parte_02_de_03.mp4
      nome-do-video_parte_03_de_03.mp4
    transcricao/
      nome-do-video_transcricao.txt
      nome-do-video_transcricao.srt
      nome-do-video_transcricao.vtt
      nome-do-video_transcricao.json
```

## Perfis de transcricao

- `Rapida`: usa modelo menor. Boa para testes.
- `Equilibrada`: melhor equilibrio entre qualidade e velocidade.
- `Maxima qualidade`: melhor resultado, mas demora mais.

Na primeira vez, o modelo pode demorar para baixar.

## Linha de comando

Dividir em 3 partes:

```powershell
python separar_video.py -i "C:\caminho\video.mp4" -p 3 --qualidade equilibrada
```

Transcrever:

```powershell
python transcrever_video.py -i "C:\caminho\video.mp4" --perfil equilibrada --idioma pt
```

## Observacoes

- Videos, transcricoes, modelos baixados e executaveis gerados nao ficam no GitHub.
- O FFmpeg precisa estar instalado no Windows ou colocado em `ferramentas/ffmpeg/bin/`.
- O desempenho depende do tamanho do video, do processador e da placa de video.

## Licenca

MIT.
