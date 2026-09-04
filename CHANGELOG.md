# Changelog

Alteracoes relevantes deste projeto sao registradas aqui. O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) de forma simplificada.

## [0.3.0] - 2026-09-04

### Adicionado

- Shell de aplicacao com navegacao persistente, paineis redimensionaveis e temas escuro/claro.
- Telas de corte, transcricao, fila e historico no mesmo fluxo de trabalho.
- Barra de comandos com `Ctrl+K`, atalhos de secao e selecao multipla nas listas.
- Cancelamento real de FFmpeg e de transcricao, com limpeza de videos parciais e checkpoint de texto.
- Tokens visuais em tres camadas e testes de resolucao/contraste dos temas.

### Alterado

- Interface antiga substituida pela mesa de trabalho compacta e orientada a timeline.
- Entrada grafica reduzida a um adaptador; processamento continua isolado nos nucleos.

### Corrigido

- Numeros da regua de tempo cortados na borda superior da timeline.
- Textos longos sobrepostos no inspetor.

## [0.2.0] - 2026-09-03

### Adicionado

- Escolha de intervalo exato para recortar, dividir ou transcrever.
- Recorte unico e divisao do intervalo em duas, tres ou quatro partes.
- Interface grafica minimalista com progresso, log recolhivel e selecao de modelo.
- Build Windows `onedir` com FFmpeg e pacote ZIP.
- Testes de intervalo, perfil de transcricao e retomada por checkpoint.
- Documentacao de arquitetura, auditoria, build, inferencia e interface.

### Alterado

- Perfil equilibrado migrado para Faster-Whisper Turbo multilingue.
- GPU configurada com `int8_float16` e fallback automatico para CPU `int8`.
- Modelos carregados sao reutilizados e downloads interrompidos podem continuar.
- Transcricoes interrompidas retomam a partir de um checkpoint compativel.

### Corrigido

- Repositorio invalido do modelo de transcricao equilibrada.
- Descoberta das DLLs CUDA no Windows.
- Empacotamento que falhava ao carregar a DLL do Python.

## 2026-05-15

### Adicionado

- Primeira versao publica do Separador de Video.
