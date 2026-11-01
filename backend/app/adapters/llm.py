"""LLMProvider port: Gemini, Claude, Ollama (Qwen) adapters.

The LLM only explains and writes. Scores are never computed by the LLM.
If no provider is reachable, generate() returns None and callers use their template version.

Which model to use is set on the Settings page (saved on the server) and falls back to env vars.
Plans:
- free (default): Gemini Flash with a free Google AI Studio key, or Qwen via Ollama (offline), or templates.
- paid: Claude, or a paid Gemini model, with your own key.
"""
from __future__ import annotations

import json
import logging
import re

import requests

from .. import config

log = logging.getLogger(__name__)

SYSTEM = ("You are the AI assistant inside HireMate, a recruiting tool for the HR team of a value-retail chain in India. "
          "Use only the facts given to you. If a fact is not given, say it is not in the data. "
          "Be concise, warm and professional. Never invent scores, dates or names.")

# provider -> (plan, label, default model, needs key)
PROVIDERS = {
    "gemini_free": ("free", "Gemini Flash (free key)", "gemini-2.5-flash", "gemini"),
    "ollama": ("free", "Qwen 2.5 on Ollama (offline, free)", "qwen2.5:7b-instruct", None),
    "template": ("free", "No AI, templates only", "", None),
    "claude": ("paid", "Claude (paid key)", "claude-sonnet-5-5", "anthropic"),
    "gemini_paid": ("paid", "Gemini Pro (paid key)", "gemini-2.5-pro", "gemini"),
}


def _ai_settings() -> dict:
    """Saved settings (server DB) on top of env defaults."""
    from .. import db
    s = db.get_setting("ai", {}) or {}
    keys = s.get("keys", {})
    provider = s.get("provider")
    if not provider:  # nothing saved yet: derive from env, free first
        p = config.LLM_PROVIDER
        provider = {"gemini": "gemini_free", "claude": "claude", "ollama": "ollama", "template": "template"}.get(p)
        if not provider:
            # default is the free plan: Gemini Flash with a free key (templates until a key is added)
            provider = "claude" if config.ANTHROPIC_API_KEY and not config.GEMINI_API_KEY else "gemini_free"
    return {
        "provider": provider,
        "model": s.get("model") or {"gemini_free": config.GEMINI_MODEL, "claude": config.CLAUDE_MODEL,
                                    "ollama": config.OLLAMA_MODEL}.get(provider, PROVIDERS[provider][2]),
        "gemini_key": keys.get("gemini") or config.GEMINI_API_KEY,
        "anthropic_key": keys.get("anthropic") or config.ANTHROPIC_API_KEY,
        "ollama_url": s.get("ollama_url") or config.OLLAMA_URL,
    }


class GeminiLLM:
    def __init__(self, key: str, model: str, paid: bool = False) -> None:
        self.key, self.model, self.paid = key, model, paid
        self.name = f"Gemini ({model}){' · paid' if paid else ' · free tier'}"

    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def _pick_model(self) -> str | None:
        """Ask Google which models this key can use and choose a Flash model."""
        r = requests.get(self.BASE, params={"key": self.key, "pageSize": 100}, timeout=config.LLM_TIMEOUT)
        r.raise_for_status()
        names = [m["name"].split("/", 1)[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        def rank(n: str):
            bad = any(x in n for x in ("lite", "image", "tts", "live", "thinking", "embedding", "audio", "preview", "exp"))
            return (bad, "flash" not in n, n != "gemini-flash-latest", n)
        good = sorted((n for n in names if n.startswith("gemini") and "flash" in n), key=rank)
        return good[0] if good else None

    @staticmethod
    def _gen_cfg(model: str, max_tokens: int) -> dict:
        cfg = {"temperature": 0.2, "maxOutputTokens": max_tokens}
        if "2.5" in model or "flash-latest" in model:
            cfg["thinkingConfig"] = {"thinkingBudget": 0}   # no hidden "thinking": answers start in about a second
        return cfg

    def stream(self, prompt: str, system: str = SYSTEM, max_tokens: int = 900):
        """Yield the answer in small pieces as Gemini writes it."""
        import json as _json
        for attempt in (0, 1):
            r = requests.post(f"{self.BASE}/{self.model}:streamGenerateContent", params={"key": self.key, "alt": "sse"},
                              stream=True, timeout=config.LLM_TIMEOUT, json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": self._gen_cfg(self.model, max_tokens)})
            if r.status_code == 404 and attempt == 0:
                alt = self._pick_model()
                if alt and alt != self.model:
                    self.model = alt
                    self.name = f"Gemini ({alt}){' · paid' if self.paid else ' · free tier'}"
                    continue
            if r.status_code >= 400:
                raise RuntimeError(f"Gemini {r.status_code} for model {self.model}: {r.text[:200]}")
            for line in r.iter_lines(decode_unicode=True):
                if line and line.startswith("data:"):
                    try:
                        parts = _json.loads(line[5:])["candidates"][0]["content"]["parts"]
                    except (KeyError, IndexError, ValueError):
                        continue
                    txt = "".join(p.get("text", "") for p in parts)
                    if txt:
                        yield txt
            return

    def _call(self, model: str, prompt: str, system: str, max_tokens: int) -> str:
        r = requests.post(f"{self.BASE}/{model}:generateContent", params={"key": self.key}, timeout=config.LLM_TIMEOUT, json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": self._gen_cfg(model, max_tokens)})
        if r.status_code >= 400:
            # never put the key (it is in the URL) into logs or errors
            raise RuntimeError(f"Gemini {r.status_code} for model {model}: {r.text[:200]}")
        return "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])

    def generate(self, prompt: str, system: str = SYSTEM, max_tokens: int = 900) -> str:
        try:
            return self._call(self.model, prompt, system, max_tokens)
        except RuntimeError as e:
            if " 404 " not in str(e) and "not found" not in str(e).lower():
                raise
            alt = self._pick_model()
            if not alt or alt == self.model:
                raise
            out = self._call(alt, prompt, system, max_tokens)
            self.model = alt
            self.name = f"Gemini ({alt}){' · paid' if self.paid else ' · free tier'}"
            log.info("Gemini model switched to %s", alt)
            return out


class ClaudeLLM:
    def __init__(self, key: str, model: str) -> None:
        self.key, self.model = key, model
        self.name = f"Claude ({model}) · paid"

    def generate(self, prompt: str, system: str = SYSTEM, max_tokens: int = 900) -> str:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=config.LLM_TIMEOUT, headers={
            "x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": max_tokens, "temperature": 0.2, "system": system,
                  "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"])


class OllamaLLM:
    def __init__(self, url: str, model: str) -> None:
        self.url, self.model = url, model
        self.name = f"Ollama ({model}) · free, offline"

    def generate(self, prompt: str, system: str = SYSTEM, max_tokens: int = 900) -> str:
        r = requests.post(f"{self.url}/api/generate", timeout=config.LLM_TIMEOUT * 3, json={
            "model": self.model, "system": system, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.2, "num_predict": max_tokens}})
        r.raise_for_status()
        return r.json()["response"]


def _ollama_up(url: str) -> bool:
    try:
        return requests.get(f"{url}/api/tags", timeout=1.5).ok
    except Exception:  # noqa: BLE001
        return False


def build(s: dict):
    p = s["provider"]
    if p == "gemini_free" and s["gemini_key"]:
        return GeminiLLM(s["gemini_key"], s["model"])
    if p == "gemini_paid" and s["gemini_key"]:
        return GeminiLLM(s["gemini_key"], s["model"], paid=True)
    if p == "claude" and s["anthropic_key"]:
        return ClaudeLLM(s["anthropic_key"], s["model"])
    if p == "ollama" and _ollama_up(s["ollama_url"]):
        return OllamaLLM(s["ollama_url"], s["model"])
    return None


_provider = None
_checked = False


def get_llm():
    global _provider, _checked
    if not _checked:
        _provider = build(_ai_settings())
        _checked = True
    return _provider


def reset() -> None:
    global _provider, _checked
    _provider, _checked = None, False


def _mask(k: str) -> str:
    return f"•••• {k[-4:]}" if k else ""


def public_settings() -> dict:
    """Safe to send to the browser: keys are masked, never returned in full."""
    s = _ai_settings()
    plan, label, _, _ = PROVIDERS[s["provider"]]
    return {"provider": s["provider"], "plan": plan, "label": label, "model": s["model"],
            "gemini_key": _mask(s["gemini_key"]), "anthropic_key": _mask(s["anthropic_key"]),
            "ollama_url": s["ollama_url"],
            "providers": {k: {"plan": v[0], "label": v[1], "default_model": v[2], "key": v[3]}
                          for k, v in PROVIDERS.items()}}


def save_settings(provider: str, model: str | None, gemini_key: str | None, anthropic_key: str | None,
                  ollama_url: str | None, clear_keys: bool = False) -> dict:
    from .. import db
    if provider not in PROVIDERS:
        raise ValueError("Unknown AI provider")
    cur = db.get_setting("ai", {}) or {}
    keys = {} if clear_keys else dict(cur.get("keys", {}))
    if gemini_key:
        keys["gemini"] = gemini_key.strip()
    if anthropic_key:
        keys["anthropic"] = anthropic_key.strip()
    db.set_setting("ai", {"provider": provider, "model": (model or "").strip() or PROVIDERS[provider][2],
                          "keys": keys, "ollama_url": (ollama_url or "").strip() or None})
    reset()
    return public_settings()


def test_connection() -> dict:
    s = _ai_settings()
    if s["provider"] == "template":
        return {"ok": True, "message": "Templates only. No AI is called, so nothing to test."}
    llm = build(s)
    if not llm:
        need = PROVIDERS[s["provider"]][3]
        return {"ok": False, "message": f"Add your {'Google AI Studio' if need == 'gemini' else 'Anthropic'} key first."
                if need else "Ollama isn't running at that address."}
    try:
        out = llm.generate("Reply with just the word OK.", max_tokens=10)
        return {"ok": True, "message": f"Connected to {llm.name}. It replied: {out.strip()[:30]}"}
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        hint = {400: "the model name may be wrong", 401: "the key is not valid", 403: "the key is not allowed",
                404: "the model name may be wrong", 429: "free limit reached, try again in a minute"}.get(code, "")
        return {"ok": False, "message": f"The AI service said no ({code}){': ' + hint if hint else ''}."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"Couldn't reach the AI service ({type(e).__name__})."}


def status() -> dict:
    llm = get_llm()
    s = _ai_settings()
    return {"provider": llm.name if llm else "Templates (no AI key set)", "connected": bool(llm),
            "plan": PROVIDERS[s["provider"]][0]}


def stream(prompt: str, system: str = SYSTEM, max_tokens: int = 900):
    """Yield text pieces. Falls back to one piece when the model cannot stream. Yields nothing on failure."""
    llm = get_llm()
    if not llm:
        return
    try:
        if hasattr(llm, "stream"):
            yield from llm.stream(prompt, system, max_tokens)
        else:
            out = llm.generate(prompt, system, max_tokens).strip()
            if out:
                yield out
    except Exception as e:  # noqa: BLE001
        log.warning("LLM stream failed (%s); falling back to template", e)


def generate(prompt: str, system: str = SYSTEM, max_tokens: int = 900) -> str | None:
    llm = get_llm()
    if not llm:
        return None
    try:
        from .. import db
        g = (db.get_setting("ai_guidelines", "") or "").strip()
        if g:
            system += "\n\nThe HR team's own guidelines (follow them unless they conflict with the facts or with "\
                      "fairness rules):\n" + g
    except Exception:  # noqa: BLE001
        pass
    try:
        out = llm.generate(prompt, system, max_tokens).strip()
        return out or None
    except Exception as e:  # noqa: BLE001
        log.warning("LLM call failed (%s); falling back to template", e)
        return None


def generate_json(prompt: str, system: str = SYSTEM, max_tokens: int = 1400):
    """Ask for JSON and validate it parses. Returns None on any failure."""
    out = generate(prompt + "\n\nReply with valid JSON only, no markdown fences.", system, max_tokens)
    if not out:
        return None
    m = re.search(r"(\{.*\}|\[.*\])", out, re.S)
    try:
        return json.loads(m.group(1) if m else out)
    except Exception:  # noqa: BLE001
        log.warning("LLM returned invalid JSON; using template")
        return None
