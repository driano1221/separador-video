# Como contribuir

## Preparar o ambiente

```powershell
git clone https://github.com/driano1221/separador-video.git
cd separador-video
powershell -ExecutionPolicy Bypass -File .\INSTALAR_WINDOWS.ps1
```

O FFmpeg pode estar no `PATH` ou em `ferramentas\ffmpeg\bin\`.

## Antes de alterar

1. Leia [a arquitetura](docs/ARQUITETURA.md).
2. Confirme qual modulo e dono do comportamento.
3. Evite duplicar regras da camada `app/` nos CLIs ou na GUI.
4. Nao adicione videos, modelos, transcricoes, builds ou caches ao Git.

## Verificar uma mudanca

```powershell
python -m unittest discover -s tests -v
python -m py_compile SeparadorVideo.pyw separar_video.py transcrever_video.py app\video_splitter_gui.py app\video_splitter_core.py app\transcription_core.py
python app\video_splitter_gui.py --self-test
git diff --check
```

Para mudancas em corte ou transcricao, execute tambem um caso curto conforme [o guia de auditoria](docs/AUDITORIA.md).

## Manter o repositorio legivel

- Prefira funcoes pequenas e os tipos `ProcessingOptions`, `ProcessingResult`, `TranscriptionOptions` e `TranscriptionResult` ja existentes.
- Mantenha Tkinter em `video_splitter_gui.py`, FFmpeg em `video_splitter_core.py` e Whisper em `transcription_core.py`.
- Adicione um teste pequeno para qualquer novo contrato ou correcao de regressao.
- Atualize `CHANGELOG.md` e o documento tecnico afetado.
- Explique dependencias novas; nao adicione uma biblioteca quando a biblioteca padrao ou o codigo existente resolver.

## Pull request

Inclua uma descricao curta do problema, a decisao tomada, os comandos de verificacao executados e qualquer risco que permaneceu. Nao inclua midia privada em capturas, logs ou arquivos de teste.
