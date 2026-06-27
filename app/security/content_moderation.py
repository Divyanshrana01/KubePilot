from __future__ import annotations

import logging
import os
import re
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

#bound how long a HuggingFace model fetch may hang. without this, a stalled CDN download
#blocks the scanner load (and therefore startup / the request) indefinitely instead of
#failing fast. set before llm-guard/transformers import huggingface_hub so it takes effect.
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "15")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "10")

#backup regex patterns in case llm-guard isnt installed, used to blank out common pii
_PII_PATTERNS: list[tuple[str, str]] = [
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[REDACTED_EMAIL]"),
    (r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[REDACTED_PHONE]"),
    (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "[REDACTED_CARD]"),
    (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[REDACTED_IP]"),
]




#tries to import llm-guard's scan_output fn, returns None if the package isnt there
def _load_moderation() -> Any | None:
    try:
        from llm_guard import scan_output
        return scan_output
    except Exception:
        logger.debug("llm-guard output scan not available; using fallback")
        return None

_SCAN_OUTPUT = _load_moderation()
_pii_scanners: list[Any] | None = None
_moderation_scanners: list[Any] | None = None
#once a scanner's model fails to load (e.g. its weights couldn't be downloaded) we flip
#these so callers stop retrying the load on every request and just use the fallback path.
#a later restart re-attempts the load (and picks the model up once it's cached locally).
_pii_load_failed = False
_moderation_load_failed = False

def _get_pii_scanners() -> list[Any] | None:
    """Lazy-build llm-guard Sensitive scanner for PII redaction; None if its model is unavailable."""
    global _pii_scanners, _pii_load_failed
    if _pii_load_failed:
        return None
    if _pii_scanners is not None:
        return _pii_scanners
    try:
        from llm_guard.output_scanners import Sensitive
        _pii_scanners = [Sensitive()]
        return _pii_scanners
    except Exception:
        logger.exception("PII scanner model unavailable; falling back to regex redaction")
        _pii_load_failed = True
        return None


#same lazy-build pattern as above but for output toxicity.
#NOTE: BanTopics is intentionally NOT used on the output path. its zero-shot classifier
#flags everyday k8s/SRE vocabulary (e.g. "OOM killer terminated the container", "force
#delete", "evict the node") as violence/illegal, which would 500 legitimate answers.
#toxicity (abusive language) is a better-calibrated signal for output. the input guard
#still runs BanTopics, where it gates user questions rather than our own generated text.
#llm-guard's output Toxicity scanner is backed by this HF model
_TOXICITY_MODEL_ID = "nicholasKluge/ToxicityModel"

def _get_moderation_scanners() -> list[Any] | None:
    global _moderation_scanners, _moderation_load_failed
    if _moderation_load_failed:
        return None
    if _moderation_scanners is not None:
        return _moderation_scanners
    try:
        #gate the build on the model's WEIGHTS being fully cached locally. local_files_only
        #only proves the snapshot dir exists - a partial download (config/tokenizer but no
        #weights) still passes it, then the scanner build hangs fetching the missing weights.
        #so we additionally require a real, non-stub weights file before building. this keeps
        #an incomplete/flaky download from looping and blocking startup; once the weights are
        #actually present, a restart loads the scanner for real.
        import os as _os
        from huggingface_hub import snapshot_download
        snap = snapshot_download(_TOXICITY_MODEL_ID, local_files_only=True)
        weights_present = any(
            _os.path.exists(_os.path.join(snap, f))
            and _os.path.getsize(_os.path.join(snap, f)) > 1_000_000
            for f in ("model.safetensors", "pytorch_model.bin")
        )
        if not weights_present:
            raise FileNotFoundError("toxicity model weights not fully cached")
        from llm_guard.output_scanners import Toxicity
        _moderation_scanners = [Toxicity(threshold=settings.output_toxicity_threshold)]
        return _moderation_scanners
    except Exception:
        #model not available locally (or failed to load) - degrade output toxicity to "allow"
        #rather than hang or crash. input guard + PII redaction stay active.
        logger.warning("Output toxicity model not cached locally; output moderation degraded to allow")
        _moderation_load_failed = True
        return None

#blanks out emails, phone numbers, card numbers and ips from the llm's answer before its sent back
def redact_pii(text: str) -> str:
    scanners = _get_pii_scanners() if _SCAN_OUTPUT is not None else None
    #scanners is None when llm-guard is absent OR its model failed to load - either way,
    #drop to the regex patterns below so PII is still redacted, just less thoroughly
    if scanners:
        try:
            sanitized, _ = _SCAN_OUTPUT(scanners, "", text)
            return str(sanitized)
        except Exception:
            logger.exception("llm-guard PII redaction failed; using regex fallback")

    for pattern, replacement in _PII_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text

def moderate_output(text: str) -> tuple[bool, str | None]:
    """Moderate LLM output text. Returns (allowed, reason_or_none).

    If blocked, reason explains why. If allowed, text is redacted in-place.
    """
    scanners = _get_moderation_scanners() if _SCAN_OUTPUT is not None else None
    #scanners is None when the toxicity model isn't available - degrade to "allow" instead
    #of blocking or hanging (the input guard already screened the question on the way in)
    if scanners:
        try:
            _, is_valid = _SCAN_OUTPUT(scanners, "", text)
            failed = [name for name, valid in is_valid.items() if not valid]
            if failed:
                checks = ", ".join(failed)
                return False, f"Output blocked by {checks}"
            return True, None
        except Exception:
            logger.exception("llm-guard output moderation failed; allowing")

    return True, None


def moderate_and_redact(text: str) -> tuple[bool, str, str | None]:
    """Moderate output and redact PII. Returns (allowed, redacted_text, reason).

    Always redacts PII even if moderation passes.
    """
    allowed, reason = moderate_output(text)
    redacted = redact_pii(text)
    return allowed, redacted, reason
