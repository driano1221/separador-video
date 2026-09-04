# Interface

## Direcao visual

Isto e uma mesa de trabalho para midia local. O usuario olha principalmente a timeline, o texto transcrito ou a lista de resultados; essa area recebe o maior espaco e o menor ruido.

A sessao pode ser longa, por isso o tema escuro e o padrao. Carvao quente, linhas de um pixel e cobre restrito a selecao/acao principal tornam a janela reconhecivel sem recorrer a estetica de site ou produto de IA. O tema claro preserva a mesma hierarquia.

## Decisoes funcionais

- Navegacao lateral persistente para corte, transcricao, fila e historico.
- Timeline dominante e horarios em `HH:MM:SS`.
- Cobre somente em selecao, foco e acao principal; verde/vermelho somente em estado.
- Progresso sempre visivel e cancelavel na barra inferior.
- Paineis laterais redimensionaveis e estado salvo em `%LOCALAPPDATA%\SeparadorVideo`.
- Menus de contexto, selecao multipla e barra de comandos com `Ctrl+K`.
- Dimensoes verificadas em 1552x832 e minimo de 980x620.
- FFmpeg no pacote e fallback automatico da transcricao para CPU.

## Referencias

- [Principios de interface do Windows](https://learn.microsoft.com/windows/win32/appuistart/-user-interface-principles)
- [Widgets tematicos nativos do Tk](https://docs.python.org/3/library/tkinter.ttk.html)
- [Estilos e temas do Tk](https://tkdocs.com/tutorial/styles.html)
- [Referencia de editor de video escuro](https://www.theskinsfactory.com/screenrecorderdarkmode)
- [Referencias de interfaces rusticas](https://dribbble.com/search/rustic-ui)
