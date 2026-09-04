# Inferencia e desempenho

## Diagnostico original

O perfil equilibrado usava `distil-large-v3`. Alem de essa familia ser voltada a ingles, o aplicativo montava um endereco de download inexistente. A tentativa falhava em toda execucao e o programa recorria ao OpenAI Whisper Turbo, mais lento neste computador.

Hardware avaliado: NVIDIA GeForce RTX 3050 Laptop com 4 GB de VRAM.

## Resultado medido

Amostra local de 120 segundos em portugues, com `beam_size=5`, VAD e palavras com timestamps:

| Caminho | Tempo de transcricao | Segmentos |
| --- | ---: | ---: |
| OpenAI Whisper Turbo anterior | aproximadamente 55 s | 44 |
| Faster-Whisper Turbo, GPU `int8_float16` | 6,6 s | 44 |
| Faster-Whisper Turbo em lote 8 | 3,0 s | 3 |

O modo em lote nao virou padrao porque produziu blocos de legenda longos e aumenta o risco de falta de memoria em uma GPU de 4 GB. O caminho escolhido foi cerca de oito vezes mais rapido na inferencia e preservou a segmentacao adequada para SRT.

Uma execucao fria completa pelo CLI, incluindo inicializacao do Python, importacoes e carga do modelo, caiu de aproximadamente 66 s para 44,6 s. No aplicativo grafico, o modelo permanece em memoria e as proximas transcricoes evitam esse custo de carga.

No teste de duas transcricoes no mesmo processo, a primeira levou 26,94 s e a segunda 4,48 s. A retomada tambem foi exercitada com um checkpoint em 42,56 s: o processamento terminou com os 44 segmentos esperados e removeu o arquivo parcial ao concluir.

Esses numeros sao uma medicao local, nao uma garantia para outros computadores ou audios.

## Configuracao atual

| Perfil | Modelo | Uso recomendado |
| --- | --- | --- |
| Rapida | Faster-Whisper Small | Testes e maquinas mais fracas. |
| Equilibrada | Faster-Whisper Turbo multilingue | Padrao recomendado para portugues. |
| Maxima qualidade | Faster-Whisper Large v3 | Maior precisao quando tempo e memoria permitem. |

Na GPU, o backend tenta CUDA `int8_float16`. Na CPU, usa `int8`. Se a inicializacao CUDA falhar, o app refaz o carregamento pela CPU.

## Melhorias implementadas

- Repositorios explicitos e validos para cada modelo Faster-Whisper.
- Cache do modelo em memoria entre transcricoes do mesmo processo.
- Cache persistente em `%LOCALAPPDATA%\SeparadorVideo\modelos`.
- Retomada automatica por checkpoint.
- Continuidade de download parcial.
- `condition_on_previous_text=False` para reduzir repeticoes e loops de timestamp.
- Deteccao das DLLs CUDA instaladas pelo PyTorch ou CUDA Toolkit.

## Reproduzir uma inferencia

```powershell
python transcrever_video.py -i "C:\caminho\video.mp4" --perfil equilibrada --idioma pt
```

O JSON final registra modelo, backend, dispositivo, tipo de computacao, duracao e segmentos. Use esses campos ao comparar resultados.

## Fontes tecnicas

- [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper)
- [Quantizacao CTranslate2](https://opennmt.net/CTranslate2/quantization.html)
- [OpenAI Whisper](https://github.com/openai/whisper)
- [Faster-Whisper Turbo](https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo)
