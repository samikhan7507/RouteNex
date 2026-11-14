"""LLM providers behind one tiny interface. All free options:
  ollama  - model runs on YOUR laptop (private, no key)            LLM_PROVIDER=ollama
  gemini  - Google free tier (free key; Google may use inputs)      LLM_PROVIDER=gemini  + GEMINI_API_KEY
  offline - built-in rule engine, no LLM at all (always works)      LLM_PROVIDER=offline
  auto    - gemini if a key is set, else ollama if it is running, else offline."""
import json, re, time, urllib.request, urllib.error
import config


class LLMError(Exception):
    pass


def _post(url, body, headers=None, timeout=40):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'ignore')}")
    except Exception as e:
        raise LLMError(str(e))


def _get(url, timeout=1.0, headers=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=timeout) as r:
            return json.load(r)
    except Exception as e:
        raise LLMError(str(e))


class Ollama:
    remote = False

    def __init__(self, host, model):
        self.host, self.model, self.label = host.rstrip("/"), model, f"ollama:{model}"

    def chat(self, system, messages, json_mode=False, max_tokens=350):
        body = {"model": self.model, "stream": False, "messages": [{"role": "system", "content": system}] + messages,
                "options": {"temperature": 0.1, "num_predict": max_tokens}, "keep_alive": "20m"}
        if json_mode:
            body["format"] = "json"
        return _post(f"{self.host}/api/chat", body, timeout=90)["message"]["content"]


class Gemini:
    remote = True
    _model_cache = None

    def __init__(self, key, model):
        self.key, self.model, self.label = key, model, f"gemini:{model}"

    def _url(self, model):
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def _pick_model(self):
        """Models get retired often; if ours is gone, pick any current Flash model that supports generateContent."""
        data = _get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", timeout=5, headers={"x-goog-api-key": self.key})
        names = [m["name"].split("/")[-1] for m in data.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
        flash = sorted([n for n in names if "flash" in n and "image" not in n and "tts" not in n and "live" not in n and "preview" not in n]) or sorted(n for n in names if "flash" in n)
        if not flash:
            raise LLMError("no usable Gemini model found for this key")
        return flash[-1]

    def chat(self, system, messages, json_mode=False, max_tokens=350):
        def call(model):
            gen = {"temperature": 0.1, "maxOutputTokens": max_tokens}
            if json_mode:
                gen["responseMimeType"] = "application/json"
            body = {"systemInstruction": {"parts": [{"text": system}]}, "generationConfig": gen,
                    "contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages]}
            d = _post(self._url(model), body, headers={"x-goog-api-key": self.key}, timeout=30)
            return d["candidates"][0]["content"]["parts"][0]["text"]
        try:
            return call(Gemini._model_cache or self.model)
        except LLMError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                Gemini._model_cache = self._pick_model()
                return call(Gemini._model_cache)
            raise


_cache = {"at": 0.0, "prov": None, "tried": False}


def get_provider():
    """-> provider or None (None = use the offline engine). Detection result is cached for 60 s."""
    mode = config.LLM_PROVIDER
    if mode == "offline":
        return None
    if time.time() - _cache["at"] < 60 and _cache["tried"]:
        return _cache["prov"]
    prov = None
    if mode in ("gemini", "auto") and config.GEMINI_API_KEY:
        prov = Gemini(config.GEMINI_API_KEY, config.GEMINI_MODEL)
    if prov is None and mode in ("ollama", "auto"):
        try:
            tags = _get(config.OLLAMA_HOST.rstrip("/") + "/api/tags", timeout=0.8)
            have = [m.get("name", "") for m in tags.get("models", [])]
            want = config.OLLAMA_MODEL
            if any(h == want or h.split(":")[0] == want.split(":")[0] for h in have):
                prov = Ollama(config.OLLAMA_HOST, next((h for h in have if h == want), next(h for h in have if h.split(":")[0] == want.split(":")[0])))
        except LLMError:
            prov = None
    _cache.update(at=time.time(), prov=prov, tried=True)
    return prov


def reset_cache():
    _cache.update(at=0.0, prov=None, tried=False)


def parse_json_loose(text):
    """Small models wrap JSON in prose / code fences. Pull out the first JSON object."""
    if not text:
        raise ValueError("empty")
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    s, e = t.find("{"), t.rfind("}")
    if s >= 0 and e > s:
        return json.loads(t[s:e + 1])
    raise ValueError("no JSON object found")


_PHONE = re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{4}[-\s]?\d{5}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def redact(text):
    """Remove phone numbers / emails before anything leaves the machine for a remote provider."""
    return _EMAIL.sub("[email]", _PHONE.sub("[phone]", text or ""))
