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
