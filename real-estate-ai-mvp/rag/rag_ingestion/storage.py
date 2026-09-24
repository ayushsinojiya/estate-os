"""Small storage boundary. Source code never follows document URLs."""
from pathlib import Path
from typing import Protocol
import os
import uuid


class Storage(Protocol):
    def save(self, workspace: str, version: str, content: bytes, extension: str) -> str: ...
    def path(self, key: str) -> Path: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, key):
        target = (self.root / key).resolve()
        if not key or target == self.root or self.root not in target.parents:
            raise ValueError('Invalid storage key')
        return target

    def save(self, workspace, version, content, extension):
        if not str(workspace).isdigit() or not extension.isalnum():
            raise ValueError('Invalid storage identity')
        key = f'{workspace}/{uuid.UUID(str(version))}/{uuid.uuid4().hex}.{extension}'
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tmp')
        try:
            with temporary.open('xb') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return key

    def delete(self, key):
        self.path(key).unlink(missing_ok=True)
