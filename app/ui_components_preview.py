"""Phase 2 visual matrix for the three anchor controls."""

from __future__ import annotations

import argparse
import tkinter as tk
from tkinter import font as tkfont

from app.ui_theme import TokenTheme, validate_tokens


STATES = (
    ("rest", "REPOUSO"),
    ("hover", "HOVER"),
    ("focus", "FOCO"),
    ("pressed", "PRESSIONADO"),
    ("selected", "SELECIONADO"),
    ("disabled", "DESABILITADO"),
    ("loading", "CARREGANDO"),
    ("error", "ERRO"),
)


class ComponentPreview:
    def __init__(self, root: tk.Tk, theme_name: str) -> None:
        self.root = root
        self.theme_name = theme_name
        self.theme = TokenTheme(theme_name)
        self.fonts: dict[tuple[str, str], tkfont.Font] = {}
        self.root.title("Componentes | SeparadorVideo")
        self.root.resizable(False, False)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.bind("<d>", lambda _event: self.set_theme("dark"))
        self.root.bind("<l>", lambda _event: self.set_theme("light"))
        self.render()

    def value(self, token: str):
        return self.theme.get(token)

    def font(self, size_token: str, weight_token: str = "font.weight.regular") -> tkfont.Font:
        cache_key = (size_token, weight_token)
        if cache_key not in self.fonts:
            weight = "bold" if self.value(weight_token) >= 600 else "normal"
            self.fonts[cache_key] = tkfont.Font(
                family=self.value("font.family.ui"),
                size=self.value(size_token),
                weight=weight,
            )
        return self.fonts[cache_key]

    def set_theme(self, theme_name: str) -> None:
        if theme_name == self.theme_name:
            return
        self.theme_name = theme_name
        self.theme = TokenTheme(theme_name)
        self.fonts.clear()
        self.render()

    def render(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()

        width = self.value("specimen.window-width")
        height = self.value("specimen.window-height")
        self.root.title(f"Componentes | SeparadorVideo | {self.theme_name}")
        self.root.geometry(f"{width}x{height}")
        self.root.configure(background=self.value("window.background"))

        header = tk.Frame(
            self.root,
            background=self.value("surface.titlebar"),
            height=self.value("size.titlebar") + self.value("space.6"),
            highlightbackground=self.value("border.subtle"),
            highlightthickness=self.value("line.1"),
        )
        header.pack(fill="x")
        header.pack_propagate(False)

        title_area = tk.Frame(header, background=self.value("surface.titlebar"))
        title_area.pack(side="left", fill="y", padx=self.value("space.6"))
        tk.Label(
            title_area,
            text="COMPONENTES-ANCORA",
            background=self.value("surface.titlebar"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.4", "font.weight.semibold"),
        ).pack(anchor="w", pady=(self.value("space.3"), 0))
        tk.Label(
            title_area,
            text="Matriz de estados  |  D: escuro  L: claro  Esc: fechar",
            background=self.value("surface.titlebar"),
            foreground=self.value("text.secondary"),
            font=self.font("font.size.1"),
        ).pack(anchor="w")

        switcher = tk.Frame(header, background=self.value("surface.titlebar"))
        switcher.pack(side="right", fill="y", padx=self.value("space.6"))
        for key, label in (("dark", "ESCURO"), ("light", "CLARO")):
            active = key == self.theme_name
            button = tk.Button(
                switcher,
                text=label,
                command=lambda value=key: self.set_theme(value),
                background=self.value("accent.primary" if active else "surface.control"),
                foreground=self.value("text.on-accent" if active else "text.primary"),
                activebackground=self.value("accent.primary-hover" if active else "surface.hover"),
                activeforeground=self.value("text.on-accent" if active else "text.primary"),
                disabledforeground=self.value("text.disabled"),
                font=self.font("font.size.1", "font.weight.semibold"),
                relief="flat",
                borderwidth=self.value("line.1"),
                highlightthickness=self.value("line.1"),
                highlightbackground=self.value("border.control"),
                highlightcolor=self.value("border.focus"),
                width=8,
                takefocus=True,
            )
            button.pack(side="left", padx=(self.value("space.2"), 0), pady=self.value("space.5"))

        table = tk.Frame(self.root, background=self.value("border.subtle"))
        table.pack(
            fill="x",
            padx=self.value("space.6"),
            pady=self.value("space.6"),
        )

        self.add_header_row(table)
        self.add_control_row(table, 1, "BOTAO", "button")
        self.add_control_row(table, 2, "CAMPO", "field")
        self.add_control_row(table, 3, "ITEM DE LISTA", "list")

    def cell(self, parent: tk.Widget, row: int, column: int, width: int, height: int) -> tk.Frame:
        frame = tk.Frame(
            parent,
            width=width,
            height=height,
            background=self.value("surface.panel"),
        )
        frame.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(self.value("line.1"), 0),
            pady=(self.value("line.1"), 0),
        )
        frame.grid_propagate(False)
        return frame

    def add_header_row(self, table: tk.Frame) -> None:
        label_width = self.value("specimen.label-width")
        cell_width = self.value("specimen.cell-width")
        height = self.value("size.control")
        corner = self.cell(table, 0, 0, label_width, height)
        tk.Label(
            corner,
            text="CONTROLE",
            anchor="w",
            padx=self.value("space.4"),
            background=self.value("surface.panel"),
            foreground=self.value("text.muted"),
            font=self.font("font.size.1", "font.weight.semibold"),
        ).pack(fill="both", expand=True)
        for column, (_state, label) in enumerate(STATES, start=1):
            frame = self.cell(table, 0, column, cell_width, height)
            tk.Label(
                frame,
                text=label,
                background=self.value("surface.panel"),
                foreground=self.value("text.muted"),
                font=self.font("font.size.1", "font.weight.semibold"),
            ).pack(fill="both", expand=True)

    def add_control_row(self, table: tk.Frame, row: int, label: str, kind: str) -> None:
        label_width = self.value("specimen.label-width")
        cell_width = self.value("specimen.cell-width")
        row_height = self.value("specimen.row-height")
        label_cell = self.cell(table, row, 0, label_width, row_height)
        tk.Label(
            label_cell,
            text=label,
            anchor="w",
            padx=self.value("space.4"),
            background=self.value("surface.panel"),
            foreground=self.value("text.primary"),
            font=self.font("font.size.2", "font.weight.semibold"),
        ).pack(fill="both", expand=True)

        for column, (state, _label) in enumerate(STATES, start=1):
            frame = self.cell(table, row, column, cell_width, row_height)
            canvas = tk.Canvas(
                frame,
                width=cell_width,
                height=row_height,
                background=self.value("surface.panel"),
                highlightthickness=0,
                borderwidth=0,
                takefocus=True,
            )
            canvas.pack(fill="both", expand=True)
            getattr(self, f"draw_{kind}")(canvas, state, cell_width, row_height)

    def control_box(self, width: int, height: int) -> tuple[int, int, int, int]:
        control_width = self.value("specimen.control-width")
        control_height = self.value("control.height")
        left = (width - control_width) // 2
        top = (height - control_height) // 2
        return left, top, left + control_width, top + control_height

    def state_colors(self, kind: str, state: str) -> tuple[str, str, str]:
        base_state = state if state in {"hover", "pressed", "selected", "disabled", "loading", "error"} else "rest"
        background = self.value(f"{kind}.background.{base_state}")
        border_token = f"{kind}.border.error" if state == "error" else f"{kind}.border.focus" if state == "focus" else f"{kind}.border.rest"
        text_token = f"{kind}.text.disabled" if state == "disabled" else f"{kind}.text.selected" if kind == "button" and state == "selected" else f"{kind}.text.rest"
        return background, self.value(border_token), self.value(text_token)

    def draw_button(self, canvas: tk.Canvas, state: str, width: int, height: int) -> None:
        left, top, right, bottom = self.control_box(width, height)
        background, border, text = self.state_colors("button", state)
        labels = {
            "selected": "Selecionado",
            "disabled": "Processar",
            "loading": "Aguarde...",
            "error": "Falhou | Repetir",
        }
        canvas.create_rectangle(left, top, right, bottom, fill=background, outline=border, width=self.value("line.1"))
        if state == "loading":
            marker_left = left + self.value("space.4")
            for offset in range(3):
                x = marker_left + offset * self.value("space.2")
                canvas.create_line(x, top + self.value("space.4"), x, bottom - self.value("space.4"), fill=self.value("accent.primary"), width=self.value("line.1"))
        canvas.create_text(
            (left + right) // 2 + (self.value("space.1") if state == "pressed" else 0),
            (top + bottom) // 2 + (self.value("space.1") if state == "pressed" else 0),
            text=labels.get(state, "Processar"),
            fill=text,
            font=self.font("font.size.2", "font.weight.semibold"),
        )

    def draw_field(self, canvas: tk.Canvas, state: str, width: int, height: int) -> None:
        left, top, right, bottom = self.control_box(width, height)
        background, border, text = self.state_colors("field", state)
        canvas.create_rectangle(left, top, right, bottom, fill=background, outline=border, width=self.value("line.1"))
        text_left = left + self.value("space.4")
        if state == "loading":
            canvas.create_rectangle(
                text_left,
                top + self.value("space.4"),
                right - self.value("space.7"),
                bottom - self.value("space.4"),
                fill=self.value("text.muted"),
                outline="",
            )
            return
        value = "08:75:00" if state == "error" else "00:08:00"
        if state == "selected":
            canvas.create_rectangle(
                text_left - self.value("space.1"),
                top + self.value("space.3"),
                text_left + self.value("space.7") * 3,
                bottom - self.value("space.3"),
                fill=self.value("selection.fill"),
                outline="",
            )
        canvas.create_text(
            text_left,
            (top + bottom) // 2,
            text=value,
            anchor="w",
            fill=text,
            font=self.font("font.size.3"),
        )
        if state == "focus":
            caret = text_left + self.value("space.7") * 2
            canvas.create_line(caret, top + self.value("space.3"), caret, bottom - self.value("space.3"), fill=self.value("text.primary"), width=self.value("line.1"))
        if state == "error":
            canvas.create_text(
                right - self.value("space.4"),
                (top + bottom) // 2,
                text="!",
                anchor="e",
                fill=self.value("status.error"),
                font=self.font("font.size.3", "font.weight.bold"),
            )

    def draw_list(self, canvas: tk.Canvas, state: str, width: int, height: int) -> None:
        left, top, right, bottom = self.control_box(width, height)
        base_state = state if state in {"hover", "pressed", "selected", "disabled", "loading", "error"} else "rest"
        background = self.value(f"list.item.background.{base_state}")
        border = self.value("border.focus" if state == "focus" else "border.error" if state == "error" else "border.subtle")
        text = self.value("list.item.text.disabled" if state == "disabled" else "list.item.text.rest")
        canvas.create_rectangle(left, top, right, bottom, fill=background, outline=border, width=self.value("line.1"))
        if state == "selected":
            canvas.create_rectangle(left, top, left + self.value("space.1"), bottom, fill=self.value("list.item.edge.selected"), outline="")
        icon_left = left + self.value("space.3")
        icon_size = self.value("space.5")
        if state == "loading":
            canvas.create_rectangle(icon_left, top + self.value("space.4"), icon_left + icon_size, bottom - self.value("space.4"), fill=self.value("text.muted"), outline="")
            canvas.create_rectangle(icon_left + self.value("space.6"), top + self.value("space.4"), right - self.value("space.6"), bottom - self.value("space.4"), fill=self.value("text.muted"), outline="")
            return
        canvas.create_rectangle(icon_left, top + self.value("space.4"), icon_left + icon_size, bottom - self.value("space.4"), outline=text, width=self.value("line.1"))
        label = "Indisponivel" if state == "error" else "reuniao..."
        canvas.create_text(
            icon_left + self.value("space.6"),
            (top + bottom) // 2,
            text=label,
            anchor="w",
            fill=text,
            font=self.font("font.size.1"),
        )
        if state == "selected":
            canvas.create_text(right - self.value("space.3"), (top + bottom) // 2, text="SEL", anchor="e", fill=self.value("accent.primary"), font=self.font("font.size.1", "font.weight.bold"))
        elif state == "error":
            canvas.create_text(right - self.value("space.3"), (top + bottom) // 2, text="!", anchor="e", fill=self.value("status.error"), font=self.font("font.size.3", "font.weight.bold"))
        else:
            canvas.create_text(right - self.value("space.3"), (top + bottom) // 2, text="58:42", anchor="e", fill=self.value("text.secondary"), font=self.font("font.size.1"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualiza os componentes-ancora da interface.")
    parser.add_argument("--theme", choices=("dark", "light"), default="dark")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_tokens()
    if args.self_test:
        print("COMPONENTS_OK")
        return
    root = tk.Tk()
    ComponentPreview(root, args.theme)
    root.mainloop()


if __name__ == "__main__":
    main()
