"""Storage backend abstraction and factory."""

from abc import ABC, abstractmethod

from app.config import settings


#the minimal key->bytes contract every backend must satisfy. callers (e.g. DocCacheService)
#only ever talk to this interface, so swapping local disk for s3 needs no change above here.
#keys are opaque strings shaped like paths ("<hash>/metadata.json"), not real filesystem paths.
class StorageBackend(ABC):
    """Generic byte storage interface used by cache services."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True when key exists."""

    @abstractmethod
    def save_bytes(self, key: str, data: bytes) -> None:
        """Persist bytes at key."""

    @abstractmethod
    def read_bytes(self, key: str) -> bytes:
        """Read bytes for key."""

    @abstractmethod
    def url_for(self, key: str) -> str:
        """Return a stable URL-like reference for key."""


#picks the concrete backend from config at call time. the imports are deliberately inside
#each branch so you only pay for (and only need installed) the one you actually use -
#e.g. the s3 path imports boto3, which local-disk deployments never have to install.
def get_storage_backend() -> StorageBackend:
    """Build a configured storage backend from settings."""
    backend = settings.storage_backend.strip().lower()
    if backend == "local":
        from app.storage.local_storage import LocalStorage

        return LocalStorage()
    if backend == "s3":
        from app.storage.s3_storage import S3Storage

        return S3Storage()
    #any value other than the two supported backends is a config mistake, fail loudly
    raise ValueError(f"Unsupported storage backend: {settings.storage_backend}")