# Guia de auditoria

Este roteiro permite revisar o projeto sem depender do historico desta conversa.

## 1. Confirmar o escopo versionado

```powershell
git status --short
git ls-files
git check-ignore -v .\saidas .\executaveis .\ferramentas\ffmpeg
```

Devem estar no Git apenas codigo, testes, documentacao, scripts de instalacao/build e assets da interface. Videos, modelos, transcricoes, executaveis e caches devem permanecer locais.

## 2. Revisar os pontos de entrada

| Uso | Entrada |
| --- | --- |
| Interface pelo fonte | `SeparadorVideo.pyw` |
| Interface auditavel com console | `python app\video_splitter_gui.py` |
| Video por CLI | `python separar_video.py --help` |
| Transcricao por CLI | `python transcrever_video.py --help` |
| Build do Windows | `CRIAR_EXECUTAVEL.ps1` |

As entradas devem apenas converter parametros e chamar os nucleos em `app/`.

## 3. Executar verificacoes rapidas

```powershell
python -m unittest discover -s tests -v
python -m py_compile SeparadorVideo.pyw separar_video.py transcrever_video.py app\video_splitter_gui.py app\video_workbench_gui.py app\video_splitter_core.py app\transcription_core.py app\ui_tokens.py app\ui_theme.py
python app\video_splitter_gui.py --self-test
git diff --check
```

Resultado esperado:

- todos os testes aprovados;
- nenhuma mensagem do `py_compile`;
- `GUI_OK` no autoteste;
- nenhuma saida em `git diff --check`.

O autoteste confirma tokens, ferramentas e imports do runtime, mas nao baixa modelo nem executa uma inferencia completa.

## 4. Testar um caso representativo

Use um arquivo curto que nao contenha dados sensiveis:

```powershell
python separar_video.py -i "C:\amostras\video.mp4" -p 2 --inicio 10 --fim 70 --output-root .\saidas_testes
python transcrever_video.py -i "C:\amostras\video.mp4" --perfil rapida --idioma pt --inicio 10 --fim 70 --output-root .\saidas_testes
```

Confira:

- dois videos cobrindo exatamente o intervalo de 10 a 70 segundos;
- TXT legivel e legendas SRT/VTT com tempos crescentes;
- JSON com `model_id`, `backend`, `device`, `compute_type` e segmentos;
- nenhum arquivo de entrada modificado.

## 5. Limites de seguranca e privacidade

- O processamento e local e o arquivo de midia nao e enviado por este codigo.
- Na primeira execucao, arquivos de modelo sao baixados de repositorios configurados no nucleo de transcricao.
- Caminhos absolutos do arquivo de entrada podem aparecer no JSON e nos logs locais.
- O app inicia FFmpeg, FFprobe e bibliotecas de inferencia instaladas ou empacotadas; a procedencia desses binarios faz parte da auditoria de distribuicao.
- Nao publique `saidas/`, logs, checkpoints, modelos ou videos de teste sem revisar o conteudo.

## 6. Checklist antes de publicar

- [ ] `git status --short` contem somente mudancas intencionais.
- [ ] Os comandos da secao 3 passam.
- [ ] Nenhum video, transcricao, modelo, executavel ou log esta versionado.
- [ ] `requirements.txt` corresponde aos imports dos nucleos e do build.
- [ ] `CHANGELOG.md` descreve a alteracao visivel.
- [ ] O ZIP foi recriado e testado em uma pasta extraida separada.
- [ ] O SHA-256 do ZIP foi registrado na release do GitHub.

## Riscos conhecidos

- O teste automatizado cobre contratos de intervalo, perfil e checkpoint, mas nao valida todos os encoders FFmpeg.
- Resultado e velocidade da transcricao variam com audio, driver, VRAM e modelo.
- O fallback OpenAI Whisper existe no fonte, mas e excluido do executavel atual para reduzir tamanho.
- Nao ha assinatura digital do executavel; o Windows pode exibir um aviso de origem desconhecida.
