"""Resolve primitive, semantic and component design-token aliases."""

from typing import Any

from app.ui_tokens import COMPONENT, PRIMITIVES, SEMANTIC


class TokenTheme:
    def __init__(self, name: str = "dark") -> None:
        if name not in SEMANTIC:
            raise ValueError(f"Tema desconhecido: {name}")
        self.name = name

    def get(self, token: str) -> Any:
        return self._resolve(token, set())

    def _resolve(self, token: str, visited: set[str]) -> Any:
        if token in visited:
            raise ValueError(f"Referencia circular de token: {token}")
        visited.add(token)

        if token in PRIMITIVES:
            return PRIMITIVES[token]
        if token in SEMANTIC[self.name]:
            return self._resolve(SEMANTIC[self.name][token], visited)
        if token in COMPONENT:
            return self._resolve(COMPONENT[token], visited)
        raise KeyError(f"Token desconhecido: {token}")


def validate_tokens() -> None:
    for theme_name in SEMANTIC:
        theme = TokenTheme(theme_name)
        for token in PRIMITIVES:
            theme.get(token)
        for token in SEMANTIC[theme_name]:
            theme.get(token)
        for token in COMPONENT:
            theme.get(token)
