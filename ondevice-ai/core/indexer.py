import os, asyncio
from typing import Iterable, Tuple
from core.orchestrator import Orchestrator


TEXT_EXT = {".txt", ".md", ".markdown"}


def iter_files(paths: Iterable[str]) -> Iterable[Tuple[str, str]]:
    for root_path in paths:
        root_path = os.path.expanduser(root_path)
        if os.path.isfile(root_path):
            yield root_path, os.path.basename(root_path)
        else:
            for r, _, files in os.walk(root_path):
                for f in files:
                    yield os.path.join(r, f), f


async def index_paths(orch: Orchestrator, paths: Iterable[str], source: str = "fs"):
    for path, name in iter_files(paths):
        ext = os.path.splitext(name)[1].lower()
        if ext not in TEXT_EXT:
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                txt = fh.read()
        except Exception:
            continue
        await orch.index_text(txt, source=f"{source}:{path}")


async def watch_and_index(orch: Orchestrator, paths: Iterable[str]):
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except Exception:
        # Watch not available; just do a one-time index
        await index_paths(orch, paths)
        return

    class Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if not event.is_directory:
                asyncio.create_task(index_paths(orch, [event.src_path], source="fs_watch"))

        def on_created(self, event):
            if not event.is_directory:
                asyncio.create_task(index_paths(orch, [event.src_path], source="fs_watch"))

    obs = Observer()
    handler = Handler()
    for p in paths:
        obs.schedule(handler, os.path.expanduser(p), recursive=True)
    obs.start()
    try:
        while True:
            await asyncio.sleep(1)
    finally:
        obs.stop()
        obs.join()
