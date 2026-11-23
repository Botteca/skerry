"""Shelf: references to files dropped on the pill, kept across restarts."""
import json
import os
import subprocess
import threading

from . import paths

MAX_ITEMS = 12


class Shelf:
    def __init__(self, path=None):
        self._path = path or paths.shelf_file()
        self._lock = threading.Lock()
        try:
            with open(self._path, encoding="utf-8") as f:
                self._items = [p for p in json.load(f) if isinstance(p, str)]
        except Exception:
            self._items = []

    def _save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._items, f, ensure_ascii=False, indent=1)

    def add(self, file_paths):
        with self._lock:
            for p in file_paths:
                p = os.path.normpath(p)
                if p in self._items:
                    self._items.remove(p)
                self._items.insert(0, p)
            self._items = self._items[:MAX_ITEMS]
            self._save()

    def remove(self, i):
        with self._lock:
            if 0 <= i < len(self._items):
                self._items.pop(i)
                self._save()

    def clear(self):
        with self._lock:
            self._items = []
            self._save()

    def get(self, i):
        with self._lock:
            return self._items[i] if 0 <= i < len(self._items) else None

    def all_paths(self):
        with self._lock:
            return [p for p in self._items if os.path.exists(p)]

    def items(self):
        with self._lock:
            out = []
            for p in self._items:
                name = os.path.basename(p) or p
                is_dir = os.path.isdir(p)
                out.append({"name": name, "ext": "dir" if is_dir else os.path.splitext(name)[1].lower().lstrip("."),
                            "exists": os.path.exists(p), "path": p})
            return out

    def open(self, i):
        p = self.get(i)
        if p and os.path.exists(p):
            os.startfile(p)

    def reveal(self, i):
        p = self.get(i)
        if p and os.path.exists(p):
            subprocess.Popen(["explorer", "/select,", p])
