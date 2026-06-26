from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.storage.storage_backend import StorageBackend, get_storage_backend

logger = logging.getLogger(__name__)

#content-addressed cache for uploaded documents: every doc is keyed by the sha256 of its
#own bytes, so re-uploading the same file (even under a different name) hashes to the same
#key and can be detected as already-processed instead of being re-ingested. the actual
#bytes/metadata live in a pluggable StorageBackend (local disk or s3), so this class only
#deals with hashing and the key layout, never with where things are physically stored.
class DocCacheService:
    #backend is injectable so tests can pass a fake; otherwise we build whatever
    #settings.storage_backend selects (see get_storage_backend)
    def __init__(self, backend: StorageBackend | None = None):
        self.backend = backend or get_storage_backend()

    def compute_content_hash(self, content: bytes) -> str:
        """Compute a sha256 hex digest from content bytes."""
        return hashlib.sha256(content).hexdigest()

    #same hash as compute_content_hash but reads the file in chunks instead of slurping it
    #all into memory, so hashing a multi-GB upload doesn't blow up the process
    def compute_file_hash(self, file_path: str | Path, chunk_size: int = 8192) -> str:
        digest = hashlib.sha256()
        path = Path(file_path)
        with path.open("rb") as file_obj:
            while True:
                chunk = file_obj.read(chunk_size)
                if not chunk:  #empty read means EOF
                    break
                digest.update(chunk)
        return digest.hexdigest()

    #everything for one document is namespaced under its hash, e.g. "<hash>/metadata.json",
    #leaving room to store sibling artifacts (extracted text, chunks, etc.) under the same prefix
    def _metadata_key(self, content_hash: str) -> str:
        return f"{content_hash}/metadata.json"

    #cheap "have we seen this document before?" check - presence of the metadata file is
    #what marks a hash as already ingested
    def exists(self, content_hash: str) -> bool:
        return self.backend.exists(self._metadata_key(content_hash))

    #writes the metadata json for a hash. swallows+logs storage errors and reports success
    #as a bool so a caching failure degrades to "just re-process it" rather than crashing ingest
    def set_metadata(self, content_hash: str, metadata: dict[str, Any]) -> bool:
        try:
            payload = json.dumps(metadata).encode("utf-8")
            self.backend.save_bytes(self._metadata_key(content_hash), payload)
            return True
        except Exception:
            logger.exception("Failed to store document metadata hash=%s", content_hash)
            return False


    def get_metadata(self, content_hash: str) -> dict[str, Any] | None:
        """Load metadata JSON for a content hash."""
        key = self._metadata_key(content_hash)
        #missing key isn't an error here - it just means this document was never cached
        if not self.backend.exists(key):
            return None

        #a corrupt/unreadable entry is treated as a cache miss (return None) so a bad
        #cached file can never wedge ingestion - worst case the doc gets reprocessed
        try:
            data = self.backend.read_bytes(key)
            return json.loads(data.decode("utf-8"))
        except Exception:
            logger.exception("Failed to read document metadata hash=%s", content_hash)
            return None