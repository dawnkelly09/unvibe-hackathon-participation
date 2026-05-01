"""lib/llm.py — minimal LLM-call shim for the hackathon-judging pipeline.

Three public functions: ``call_model``, ``call_model_with_record``,
``call_model_for_json``. Backends are selected from a model string of
the form ``<backend>:<model-name>``; the model-name portion may itself
contain colons (``ollama:qwen2.5:7b``), so the prefix is split on the
FIRST colon only.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OLLAMA_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_TIMEOUT_SECONDS = 60
_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


class LLMCallError(Exception):
    """Raised when a model call fails for any reason."""


class LLMJSONParseError(LLMCallError):
    """Raised when ``call_model_for_json`` can't parse a response after retries."""


def call_model(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 4096,
) -> str:
    """Send ``prompt`` to a model and return the response text.

    Backend is read from ``model`` if given, else the ``MODEL`` env var.
    """
    backend, name = _resolve_model(model)
    if backend == "ollama":
        return _call_ollama(name, prompt, system, max_tokens)
    if backend == "anthropic":
        return _call_anthropic(name, prompt, system, max_tokens)
    raise LLMCallError(f"Unknown backend '{backend}' (model='{backend}:{name}').")


def call_model_with_record(
    prompt: str,
    *,
    record_dir: Path,
    record_label: str,
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 4096,
) -> str:
    """Like ``call_model`` but persists a JSON record of the call.

    The record is written whether the call succeeds or fails; on
    failure the original ``LLMCallError`` is then re-raised.
    """
    resolved = model if model is not None else os.environ.get("MODEL")
    started = time.monotonic()
    timestamp = datetime.now(timezone.utc)
    response_text: str | None = None
    error_msg: str | None = None
    try:
        response_text = call_model(prompt, model=model, system=system, max_tokens=max_tokens)
        return response_text
    except LLMCallError as exc:
        error_msg = str(exc)
        raise
    finally:
        _write_record(record_dir, record_label, timestamp, {
            "timestamp": timestamp.isoformat(),
            "model": resolved,
            "label": record_label,
            "system": system,
            "prompt": prompt,
            "response": response_text,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "error": error_msg,
        })


def call_model_for_json(
    prompt: str,
    *,
    record_dir: Path,
    record_label: str,
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 4096,
    max_retries: int = 2,
) -> dict:
    """Call a model expecting JSON; retry on parse failure.

    Each attempt produces its own record file. The retry prompt asks
    for valid JSON only and does NOT include the failed response —
    fresh attempts work better than asking the model to fix.
    """
    attempts = 1 + max_retries
    last_error = ""
    for attempt in range(attempts):
        if attempt == 0:
            this_prompt, this_label = prompt, record_label
        else:
            this_prompt = (
                "Your previous response was not valid JSON. Respond with "
                "valid JSON only — no prose, no code fences, no commentary.\n\n"
                + prompt
            )
            this_label = f"{record_label}-retry-{attempt}"
        response = call_model_with_record(
            this_prompt, record_dir=record_dir, record_label=this_label,
            model=model, system=system, max_tokens=max_tokens,
        )
        try:
            return json.loads(_strip_json_artifacts(response))
        except json.JSONDecodeError as exc:
            last_error = str(exc)
    raise LLMJSONParseError(
        f"call_model_for_json failed for label='{record_label}' "
        f"after {attempts} attempt(s): {last_error}"
    )


def _resolve_model(model: str | None) -> tuple[str, str]:
    chosen = model if model is not None else os.environ.get("MODEL")
    if not chosen:
        raise LLMCallError(
            "No model specified. Pass `model=` or set the MODEL environment variable."
        )
    backend, _, name = chosen.partition(":")
    if not backend or not name:
        raise LLMCallError(f"Invalid model string '{chosen}': expected '<backend>:<name>'.")
    return backend, name


def _call_ollama(model_name: str, prompt: str, system: str | None, max_tokens: int) -> str:
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_ENDPOINT, data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        if exc.code == 404:
            raise LLMCallError(
                f"Ollama returned 404 — model '{model_name}' may not be pulled. "
                f"Run `ollama pull {model_name}`."
            ) from exc
        raise LLMCallError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, ConnectionRefusedError) or "refused" in str(reason).lower():
            raise LLMCallError(
                "Ollama daemon not reachable at localhost:11434 — is "
                "`ollama serve` running, or is the Ollama app open?"
            ) from exc
        raise LLMCallError(f"Ollama request failed: {reason}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMCallError(f"Ollama returned non-JSON response: {raw[:200]}") from exc
    try:
        return data["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise LLMCallError(f"Ollama response missing 'message.content': {raw[:200]}") from exc


def _call_anthropic(model_name: str, prompt: str, system: str | None, max_tokens: int) -> str:
    try:
        from anthropic import (
            NOT_GIVEN, Anthropic, APIError, AuthenticationError, RateLimitError,
        )
    except ImportError as exc:
        raise LLMCallError("anthropic SDK not installed. Add `anthropic` to dependencies.") from exc
    client = Anthropic()
    try:
        response = client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            system=system if system else NOT_GIVEN,
            messages=[{"role": "user", "content": prompt}],
        )
    except AuthenticationError as exc:
        raise LLMCallError("ANTHROPIC_API_KEY not set or invalid.") from exc
    except RateLimitError as exc:
        headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
        retry_after = headers.get("retry-after")
        suffix = f" (retry-after: {retry_after}s)" if retry_after else ""
        raise LLMCallError(f"Anthropic rate-limited{suffix}: {exc}") from exc
    except APIError as exc:
        raise LLMCallError(f"Anthropic API error: {exc}") from exc
    try:
        return response.content[0].text
    except (IndexError, AttributeError) as exc:
        raise LLMCallError(f"Anthropic response shape unexpected: {response!r}") from exc


def _strip_json_artifacts(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        s = s[nl + 1:] if nl != -1 else ""
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


def _write_record(record_dir: Path, label: str, timestamp: datetime, record: dict) -> None:
    record_dir.mkdir(parents=True, exist_ok=True)
    fname_ts = timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")
    slug = _SLUG_RE.sub("-", label).strip("-").lower()
    path = record_dir / f"{fname_ts}-{slug}.json"
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(record_dir))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
