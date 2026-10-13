# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "markitdown[all]",
#     "gradio",
# ]
# ///
"""MarkItDown GUI: a local desktop front end for microsoft/markitdown."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import gradio as gr
from markitdown import (
    FileConversionException,
    MarkItDown,
    UnsupportedFormatException,
)

# Creating the converter is slow (it loads file-type detection models), so do it once.
# Plugins stay disabled so behavior matches the plain markitdown library.
_converter = MarkItDown(enable_plugins=False)


@dataclass
class Result:
    """Outcome of converting a single file. Exactly one of markdown/error is set."""

    name: str
    markdown: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def convert_file(path: str | Path) -> str:
    """Convert one file to Markdown text. Raises on failure."""
    return _converter.convert(Path(path)).text_content


def convert_files(paths: Iterable[str | Path]) -> list[Result]:
    """Convert several files, capturing per-file errors so one bad file
    does not abort the whole batch."""
    results = []
    for path in paths:
        name = Path(path).name
        try:
            results.append(Result(name, markdown=convert_file(path)))
        except Exception as exc:  # noqa: BLE001 - any failure is reported per file
            results.append(Result(name, error=_describe_error(exc)))
    return results


def _describe_error(exc: Exception) -> str:
    """Turn a conversion exception into a short message for end users."""
    if isinstance(exc, UnsupportedFormatException):
        return "Unsupported file format."
    if isinstance(exc, FileConversionException):
        return "Could not convert this file. It may be corrupted or password-protected."
    if isinstance(exc, FileNotFoundError):
        return "File not found."
    return f"Unexpected error ({type(exc).__name__}): {exc}"


# --- UI ---------------------------------------------------------------------

# All user-facing strings live here so wording changes (or a future translation)
# touch one place only.
TEXT = {
    "title": "MarkItDown GUI",
    "subtitle": (
        "Convert PDF, Word, Excel, PowerPoint, HTML and more to Markdown. "
        "Files are processed locally and never leave your computer."
    ),
    "upload": "File to convert",
    "convert": "Convert",
    "preview_tab": "Preview",
    "source_tab": "Markdown",
    "no_file": "Please choose a file first.",
}


def on_convert(path: str | None) -> tuple[str, str]:
    """Gradio handler: return (rendered preview, raw markdown)."""
    if not path:
        gr.Warning(TEXT["no_file"])
        return "", ""
    result = convert_files([path])[0]
    if not result.ok:
        gr.Warning(f"{result.name}: {result.error}")
        return "", ""
    return result.markdown, result.markdown


def build_ui() -> gr.Blocks:
    # Files never leave the machine, and neither should usage statistics.
    with gr.Blocks(title=TEXT["title"], analytics_enabled=False) as demo:
        gr.Markdown(f"# {TEXT['title']}\n{TEXT['subtitle']}")
        file_input = gr.File(label=TEXT["upload"], type="filepath")
        convert_button = gr.Button(TEXT["convert"], variant="primary")
        with gr.Tabs():
            with gr.Tab(TEXT["preview_tab"]):
                preview = gr.Markdown()
            with gr.Tab(TEXT["source_tab"]):
                source = gr.Code(language="markdown", interactive=False)
        convert_button.click(on_convert, inputs=file_input, outputs=[preview, source])
    return demo


if __name__ == "__main__":
    build_ui().launch(
        server_name="127.0.0.1",  # never expose to the network
        inbrowser=True,
        share=False,
    )
