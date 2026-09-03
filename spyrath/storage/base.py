from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
import shutil

class ArtifactStorage(ABC):
    @abstractmethod
    def put(self, source: Path, key: str) -> Path: ...
    @abstractmethod
    def resolve(self, key: str) -> Path: ...

class LocalArtifactStorage(ArtifactStorage):
    """Durable filesystem storage boundary; cloud adapters can implement the same contract."""
    def __init__(self, root: str | Path): self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
    def _path(self,key:str)->Path:
        p=(self.root/key).resolve(); root=self.root.resolve()
        if root not in p.parents and p != root: raise ValueError('storage key escapes root')
        return p
    def put(self,source:Path,key:str)->Path:
        dest=self._path(key); dest.parent.mkdir(parents=True,exist_ok=True); tmp=dest.with_name(dest.name+'.tmp'); shutil.copy2(source,tmp); tmp.replace(dest); return dest
    def resolve(self,key:str)->Path: return self._path(key)
