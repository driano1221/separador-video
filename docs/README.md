# Documentacao tecnica

Este diretorio e o ponto de entrada para quem precisa entender, auditar, testar ou distribuir o Separador de Video.

| Documento | Quando consultar |
| --- | --- |
| [Arquitetura](ARQUITETURA.md) | Para entender componentes, responsabilidades e o fluxo completo dos dados. |
| [Auditoria](AUDITORIA.md) | Para revisar o repositorio, validar comportamento e identificar dados locais. |
| [Build e distribuicao](BUILD_E_DISTRIBUICAO.md) | Para gerar e verificar o executavel do Windows. |
| [Inferencia](INFERENCIA.md) | Para entender modelos, GPU, fallback, cache e resultados medidos. |
| [Interface](INTERFACE.md) | Para entender as decisoes visuais e funcionais da GUI. |

Documentos gerais na raiz:

- [README](../README.md): uso e instalacao.
- [CONTRIBUTING](../CONTRIBUTING.md): fluxo de manutencao.
- [CHANGELOG](../CHANGELOG.md): alteracoes relevantes.
- [LICENSE](../LICENSE): licenca MIT.

## Regra de atualizacao

Uma mudanca deve atualizar o documento que e dono daquela informacao:

- comportamento para o usuario: `README.md`;
- responsabilidade ou fluxo entre modulos: `docs/ARQUITETURA.md`;
- dependencias, empacotamento ou distribuicao: `docs/BUILD_E_DISTRIBUICAO.md`;
- modelo, backend, GPU ou desempenho: `docs/INFERENCIA.md`;
- procedimento verificavel: `docs/AUDITORIA.md`;
- historico resumido: `CHANGELOG.md`.
