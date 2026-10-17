# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "markitdown[docx,pdf,pptx,xls,xlsx,outlook]",
#     "gradio",
# ]
# ///
# Extras are listed instead of markitdown[all] on purpose: "all" adds audio
# transcription that uploads audio to Google's speech API, plus Azure and
# YouTube clients. Files must never leave the user's computer.
"""MarkItDown GUI: a local desktop front end for microsoft/markitdown."""

from __future__ import annotations

import html
import os
import shutil
import tempfile
import threading
import zipfile
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
            markdown = convert_file(path)
        except Exception as exc:  # noqa: BLE001 - any failure is reported per file
            results.append(Result(name, error=_describe_error(exc)))
            continue
        if markdown.strip():
            results.append(Result(name, markdown=markdown))
        else:
            # Images and audio yield nothing without OCR/transcription, which
            # would need online services; say so instead of showing "100%".
            results.append(Result(name, error=NO_TEXT_ERROR))
    return results


NO_TEXT_ERROR = (
    "No text could be extracted. Images and audio are not transcribed, "
    "because that would require sending them to an online service."
)


def _describe_error(exc: Exception) -> str:
    """Turn a conversion exception into a short message for end users."""
    if isinstance(exc, UnsupportedFormatException):
        return "Unsupported file format."
    if isinstance(exc, FileConversionException):
        return "Could not convert this file. It may be corrupted or password-protected."
    if isinstance(exc, FileNotFoundError):
        return "File not found."
    return f"Unexpected error ({type(exc).__name__}): {exc}"


# --- Output files -------------------------------------------------------------

# Converted files are written here before Gradio copies them into its own cache.
# A fixed location (instead of a fresh mkdtemp) means leftovers from a previous
# session that was killed without cleanup get removed on the next conversion.
OUTPUT_DIR = Path(tempfile.gettempdir()) / "markitdown-gui" / "output"
ZIP_NAME = "markdown.zip"


def markdown_filename(source_name: str, taken: set[str]) -> str:
    """Swap the extension for .md, numbering duplicates
    (report.pdf and report.docx would otherwise both become report.md)."""
    stem = Path(source_name).stem
    candidate = f"{stem}.md"
    n = 2
    while candidate in taken:
        candidate = f"{stem} ({n}).md"
        n += 1
    taken.add(candidate)
    return candidate


def write_outputs(results: list[Result]) -> dict[str, Path]:
    """Write each successful result to OUTPUT_DIR and return {md filename: path}."""
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for result in results:
        if not result.ok:
            continue
        name = markdown_filename(result.name, set(written))
        path = OUTPUT_DIR / name
        path.write_text(result.markdown, encoding="utf-8")
        written[name] = path
    return written


def write_zip(files: dict[str, Path]) -> Path:
    zip_path = OUTPUT_DIR / ZIP_NAME
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, path in files.items():
            zf.write(path, arcname=name)
    return zip_path


# --- UI ---------------------------------------------------------------------

# All user-facing strings live here so wording changes (or a future translation)
# touch one place only.
TEXT = {
    "title": "MarkItDown GUI",
    "subtitle": (
        "Convert PDF, Word, Excel, PowerPoint, HTML and more to Markdown. "
        "Files are processed locally and never leave your computer."
    ),
    "upload": "Add files (drop here or click to browse)",
    "convert": "Convert",
    "clear": "Clear list",
    "quit": "Quit",
    "downloads": "Download",
    "select_file": "Show file",
    "preview_tab": "Preview",
    "source_tab": "Markdown",
    "empty_list": "No files added yet.",
    "waiting": "Waiting",
    "converting": "Converting...",
    "done": "100%",
    "error": "Error",
    "no_file": "Please add at least one file.",
    "stopped": (
        "### MarkItDown GUI has stopped.\n"
        "You can close this browser tab. Launch the app again to convert more files."
    ),
}

# Cleanup cadence for files Gradio keeps (uploads, downloads): every hour, delete
# anything older than an hour. Gradio also clears them on a clean shutdown.
CACHE_CLEANUP = (3600, 3600)

CSS = """
.mdg-list { display: flex; flex-direction: column; gap: 10px; }
.mdg-empty { color: var(--body-text-color-subdued); text-align: center; padding: 8px; }
.mdg-row {
    display: grid; grid-template-columns: minmax(0, 1fr) minmax(120px, 45%);
    column-gap: 12px; row-gap: 2px; align-items: center;
}
.mdg-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mdg-bar {
    position: relative; height: 22px; border-radius: 999px; overflow: hidden;
    background: var(--background-fill-secondary);
    border: 1px solid var(--border-color-primary);
}
.mdg-fill { position: absolute; inset: 0; width: 0; }
.mdg-label {
    position: relative; display: flex; height: 100%; align-items: center;
    justify-content: center; font-size: 12px; font-weight: 600;
    color: var(--body-text-color-subdued);
}
.mdg-running .mdg-fill {
    width: 100%; opacity: 0.25; background-size: 28px 28px;
    background-image: repeating-linear-gradient(
        45deg, var(--color-accent) 0 7px, transparent 7px 14px);
    animation: mdg-stripes 1s linear infinite;
}
.mdg-done .mdg-fill { width: 100%; background: #16a34a; }
.mdg-error .mdg-fill { width: 100%; background: #dc2626; }
.mdg-running .mdg-label { color: var(--body-text-color); }
.mdg-done .mdg-label, .mdg-error .mdg-label { color: #fff; }
.mdg-msg { grid-column: 1 / -1; font-size: 12px; color: #dc2626; }
@keyframes mdg-stripes { to { background-position: 28px 0; } }
"""


@dataclass
class Item:
    """A file in the conversion list. `result` stays None until converted."""

    path: str
    name: str
    result: Result | None = None


def render_list(items: list[Item], running: Item | None = None) -> str:
    """Render one progress bar per file as HTML."""
    if not items:
        return f'<div class="mdg-empty">{TEXT["empty_list"]}</div>'
    rows = []
    for item in items:
        message = ""
        if item is running:
            state, label = "running", TEXT["converting"]
        elif item.result is None:
            state, label = "waiting", TEXT["waiting"]
        elif item.result.ok:
            state, label = "done", TEXT["done"]
        else:
            state, label = "error", TEXT["error"]
            message = f'<div class="mdg-msg">{html.escape(item.result.error)}</div>'
        name = html.escape(item.name)
        rows.append(
            f'<div class="mdg-row"><div class="mdg-name" title="{name}">{name}</div>'
            f'<div class="mdg-bar mdg-{state}"><div class="mdg-fill"></div>'
            f'<span class="mdg-label">{label}</span></div>{message}</div>'
        )
    return f'<div class="mdg-list">{"".join(rows)}</div>'


def on_add(new_paths: list[str] | None, items: list[Item]):
    """Append dropped files to the list and empty the drop zone so it keeps
    accepting drag and drop (a filled gr.File no longer does)."""
    seen = {(i.name, os.path.getsize(i.path)) for i in items}
    for path in new_paths or []:
        key = (Path(path).name, os.path.getsize(path))
        if key not in seen:  # ignore the same file dropped twice
            seen.add(key)
            items.append(Item(path, key[0]))
    return None, items, render_list(items)


def on_clear():
    hidden = gr.Dropdown(choices=[], value=None, visible=False)
    return [], render_list([]), gr.File(value=None, visible=False), hidden, {}, "", ""


def on_convert(items: list[Item]):
    """Convert files that have not been converted yet, updating the progress
    bars after each one, then refresh the downloads and preview."""
    skip = gr.skip()
    if not items:
        gr.Warning(TEXT["no_file"])
        # Ending without a yield would blank every output, so leave them as is.
        yield skip, skip, skip, skip, skip, skip, skip
        return
    for item in items:
        if item.result is None:
            yield items, render_list(items, running=item), skip, skip, skip, skip, skip
            item.result = convert_files([item.path])[0]

    files = write_outputs([i.result for i in items])
    markdown_by_name = {
        name: path.read_text(encoding="utf-8") for name, path in files.items()
    }
    downloads = [str(p) for p in files.values()]
    if len(files) > 1:
        downloads.insert(0, str(write_zip(files)))

    names = list(markdown_by_name)
    first = names[0] if names else None
    first_md = markdown_by_name.get(first, "")
    yield (
        items,
        render_list(items),
        # Shown only once there is something to download.
        gr.File(value=downloads or None, visible=bool(downloads)),
        # The selector only matters when there is more than one file to look at.
        gr.Dropdown(choices=names, value=first, visible=len(names) > 1),
        markdown_by_name,
        first_md,
        first_md,
    )


def on_select(name: str | None, markdown_by_name: dict[str, str]) -> tuple[str, str]:
    text = markdown_by_name.get(name, "") if name else ""
    return text, text


def shutdown_server(demo: gr.Blocks) -> None:
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    # A clean shutdown lets Gradio delete its cached uploads. It can end the
    # process itself, so anything that must run goes before this call.
    demo.close()
    os._exit(0)  # launch() blocks the main thread; nothing else will end it


def on_quit(demo: gr.Blocks) -> str:
    """Stop the server shortly after replying, so the page can show the message
    if the browser refuses to close the tab."""
    threading.Timer(0.5, shutdown_server, args=(demo,)).start()
    return TEXT["stopped"]


# Browsers only let a script close a tab it opened itself or one with a single
# history entry. The tab opened at launch qualifies; otherwise the "stopped"
# message stays visible instead.
CLOSE_TAB_JS = "() => { setTimeout(() => window.close(), 800); }"


class AutoShutdown:
    """Stop the server once no browser tab is connected.

    Closing the browser tab does not stop a Gradio server, and the desktop
    launcher has no terminal window to close, so without this the app would
    keep running in the background. A page refresh also drops the connection
    briefly, hence the grace period before shutting down.
    """

    GRACE_SECONDS = 10

    def __init__(self, demo: gr.Blocks) -> None:
        self._demo = demo
        self._lock = threading.Lock()
        self._open_tabs = 0
        self._timer: threading.Timer | None = None

    def tab_opened(self) -> None:
        with self._lock:
            self._open_tabs += 1
            if self._timer:
                self._timer.cancel()
                self._timer = None

    def tab_closed(self) -> None:
        with self._lock:
            self._open_tabs = max(0, self._open_tabs - 1)
            if self._open_tabs == 0 and not self._timer:
                self._timer = threading.Timer(
                    self.GRACE_SECONDS, self._shutdown_if_idle
                )
                self._timer.daemon = True
                self._timer.start()

    def _shutdown_if_idle(self) -> None:
        with self._lock:
            self._timer = None
            if self._open_tabs:
                return
        shutdown_server(self._demo)


def build_ui() -> gr.Blocks:
    # Files never leave the machine, and neither should usage statistics.
    with gr.Blocks(
        title=TEXT["title"], analytics_enabled=False, delete_cache=CACHE_CLEANUP
    ) as demo:
        items_state = gr.State([])
        markdown_state = gr.State({})
        with gr.Row():
            gr.Markdown(f"# {TEXT['title']}\n{TEXT['subtitle']}")
            quit_button = gr.Button(
                TEXT["quit"], variant="stop", size="sm", scale=0, min_width=80
            )
        stopped_notice = gr.Markdown()
        with gr.Row():
            with gr.Column():
                drop_zone = gr.File(
                    label=TEXT["upload"],
                    file_count="multiple",
                    type="filepath",
                    height=140,
                )
                file_list = gr.HTML(render_list([]))
                with gr.Row():
                    clear_button = gr.Button(TEXT["clear"])
                    convert_button = gr.Button(TEXT["convert"], variant="primary")
                downloads = gr.File(
                    label=TEXT["downloads"],
                    file_count="multiple",
                    interactive=False,
                    visible=False,
                )
            with gr.Column():
                selector = gr.Dropdown(label=TEXT["select_file"], visible=False)
                with gr.Tabs():
                    with gr.Tab(TEXT["preview_tab"]):
                        preview = gr.Markdown()
                    with gr.Tab(TEXT["source_tab"]):
                        source = gr.Code(language="markdown", interactive=False)

        drop_zone.upload(
            on_add,
            inputs=[drop_zone, items_state],
            outputs=[drop_zone, items_state, file_list],
            show_progress="hidden",
        )
        result_outputs = [downloads, selector, markdown_state, preview, source]
        clear_button.click(on_clear, outputs=[items_state, file_list, *result_outputs])
        convert_button.click(
            on_convert,
            inputs=items_state,
            outputs=[items_state, file_list, *result_outputs],
            show_progress="hidden",  # the per-file bars are the progress display
        )
        selector.change(
            on_select, inputs=[selector, markdown_state], outputs=[preview, source]
        )
        quit_button.click(
            lambda: on_quit(demo), outputs=stopped_notice, js=CLOSE_TAB_JS
        )

        auto_shutdown = AutoShutdown(demo)
        demo.load(auto_shutdown.tab_opened)
        demo.unload(auto_shutdown.tab_closed)
    return demo


if __name__ == "__main__":
    build_ui().launch(
        server_name="127.0.0.1",  # never expose to the network
        inbrowser=True,
        share=False,
        css=CSS,
    )
