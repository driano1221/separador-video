# Arquitetura

## Visao geral

O projeto e um aplicativo desktop local para Windows. Ele recebe um arquivo de video ou audio, executa FFmpeg e/ou Whisper no proprio computador e grava os resultados em uma pasta escolhida pelo usuario.

```text
SeparadorVideo.pyw ou app/video_splitter_gui.py
                  |
                  +--> app/video_splitter_core.py --> FFprobe/FFmpeg --> videos
                  |
                  +--> app/transcription_core.py --> Faster-Whisper --> TXT/SRT/VTT/JSON
```

Nao existe servidor, banco de dados ou API propria. A rede e usada para baixar um modelo na primeira transcricao; a inferencia ocorre localmente.

## Estrutura versionada

```text
.
|-- app/
|   |-- __init__.py
|   |-- transcription_core.py
|   |-- video_splitter_core.py
|   `-- video_splitter_gui.py
|-- assets/
|   |-- SeparadorVideo.ico
|   |-- SeparadorVideo.png
|   |-- interface_corte.png
|   `-- interface_transcricao.png
|-- docs/
|-- tests/
|   `-- test_transcription_core.py
|-- SeparadorVideo.pyw
|-- separar_video.py
|-- transcrever_video.py
|-- INSTALAR_WINDOWS.ps1
|-- CRIAR_EXECUTAVEL.ps1
`-- requirements.txt
```

## Responsabilidades

| Componente | Responsabilidade | Nao deve conter |
| --- | --- | --- |
| `SeparadorVideo.pyw` | Preparar o diretorio e abrir a GUI sem console. | Regras de corte ou transcricao. |
| `app/video_splitter_gui.py` | Interface, validacao de campos, threads e exibicao de progresso. | Implementacao de FFmpeg ou Whisper. |
| `app/video_splitter_core.py` | Intervalos, divisao, escolha de encoder, comandos FFmpeg e progresso. | Widgets ou mensagens de janela. |
| `app/transcription_core.py` | Modelos, download, GPU/CPU, checkpoint e formatos de transcricao. | Widgets ou parsing de argumentos CLI. |
| `separar_video.py` | Adaptar argumentos do terminal para `ProcessingOptions`. | Duplicar a logica do nucleo. |
| `transcrever_video.py` | Adaptar argumentos do terminal para `TranscriptionOptions`. | Duplicar a logica do nucleo. |
| `tests/` | Provar contratos estaveis sem depender de videos grandes. | Midia real, modelos ou artefatos gerados. |

## Fluxo de corte e divisao

1. A GUI ou o CLI cria `ProcessingOptions`.
2. `process_video` usa FFprobe para obter duracao e streams.
3. `resolve_time_range` valida inicio e fim.
4. `build_segments` calcula um recorte unico ou partes iguais.
5. `resolve_encoder` tenta a opcao solicitada ou escolhe um encoder disponivel.
6. FFmpeg processa os segmentos e emite progresso.
7. O nucleo retorna `ProcessingResult` com caminhos, encoder e tamanhos.

Contrato importante: os tempos dos segmentos continuam referenciando o video original, mesmo quando apenas um intervalo e selecionado.

## Fluxo de transcricao

1. A GUI ou o CLI cria `TranscriptionOptions`.
2. FFprobe valida o arquivo e limita o intervalo.
3. O perfil e traduzido para um repositorio Faster-Whisper.
4. O modelo e baixado para `%LOCALAPPDATA%\SeparadorVideo\modelos` quando necessario.
5. O backend escolhe CUDA `int8_float16` quando o runtime esta disponivel; caso contrario usa CPU `int8`.
6. Segmentos parciais sao salvos em checkpoint e podem ser retomados.
7. Ao concluir, o nucleo grava `.txt`, `.srt`, `.vtt` e `.json` e remove o checkpoint.

Contrato importante: um checkpoint so pode ser retomado quando arquivo, modelo, idioma, tarefa e intervalo ainda correspondem.

## Saidas e estado local

Por padrao, resultados ficam em `saidas/<nome-do-arquivo>/`. Intervalos recebem identificacao no caminho e divisoes usam pastas como `2_partes` ou `3_partes`.

Itens deliberadamente fora do Git:

- videos, audios e transcricoes em `saidas/`;
- modelos em `%LOCALAPPDATA%\SeparadorVideo\modelos`;
- FFmpeg local em `ferramentas/ffmpeg/`;
- cache de encoder em `ferramentas/encoder_cache.json`;
- builds em `executaveis/`, `artifacts/` e `ferramentas/build_novo/`.

## Dependencias externas

- FFmpeg/FFprobe: leitura, corte, divisao e compressao.
- Faster-Whisper e CTranslate2: inferencia principal.
- Hugging Face Hub: download e cache dos modelos.
- OpenAI Whisper e PyTorch: fallback disponivel ao executar pelo codigo-fonte.
- Tkinter: interface grafica nativa.
- PyInstaller: geracao do pacote Windows.
