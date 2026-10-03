"""Original upload bytes on a volume (RAG_STORAGE_PATH), addressed by opaque keys."""

from __future__ import annotations

import os
import uuid
from pathlib import Path


class FileStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def key(self, workspace_id: int, source_id: uuid.UUID, sha256: str, extension: str) -> str:
        """A fresh key per stored version; the version number is not known until the row exists."""
        return f"ws-{workspace_id}/{source_id}/{uuid.uuid4().hex[:12]}-{sha256[:12]}{extension}"

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not str(path).startswith(str(self.root) + os.sep):
            raise ValueError("unsafe storage key")
        return path

    def write(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass
