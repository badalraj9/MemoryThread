"""
Contradiction Classification Framework.

Three classifier tiers:
  1. APIProviderClassifier — calls OpenAI/Anthropic LLM
  2. LocalNLClassifier — runs cross-encoder NLI model locally (requires sentence-transformers)
  3. LightweightClassifier — heuristic keyword overlap fallback (no deps)

Factory: get_classifier() picks the right one based on settings.CONTRADICTION_MODE.
"""

from abc import ABC, abstractmethod
from typing import Tuple, Optional
import logging

from memory_thread.config.settings import settings
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

CONTRADICTION = "CONTRADICTION"
ENTAILMENT = "ENTAILMENT"
NEUTRAL = "NEUTRAL"

VALID_LABELS = {CONTRADICTION, ENTAILMENT, NEUTRAL}


class ContradictionClassifier(ABC):
    @abstractmethod
    def classify(self, text_a: str, text_b: str) -> Tuple[str, float]: ...


class APIProviderClassifier(ContradictionClassifier):
    def __init__(self, provider: Optional[str] = None):
        self.provider = (provider or settings.CONTRADICTION_API_PROVIDER or "openai").lower()

    def classify(self, text_a: str, text_b: str) -> Tuple[str, float]:
        if self.provider == "openai":
            return self._classify_openai(text_a, text_b)
        elif self.provider == "anthropic":
            return self._classify_anthropic(text_a, text_b)
        else:
            log.warning("Unknown API provider '%s', falling back to lightweight", self.provider)
            return LightweightClassifier().classify(text_a, text_b)

    def _call_llm(self, prompt: str, model: str, api_key: str, api_url: str) -> Optional[str]:
        try:
            import httpx

            resp = httpx.post(
                api_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens": 10,
                },
                timeout=15.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                    .upper()
                )
            else:
                log.warning("API call failed: %s %s", resp.status_code, resp.text)
                return None
        except ImportError:
            log.warning("httpx not installed, cannot call API provider")
            return None
        except Exception as e:
            log.warning("API call error: %s", e)
            return None

    def _classify_openai(self, text_a: str, text_b: str) -> Tuple[str, float]:
        api_key = getattr(settings, "OPENAI_API_KEY", None) or settings.MT_API_KEY
        if not api_key:
            log.warning("No OpenAI API key configured, falling back to lightweight")
            return LightweightClassifier().classify(text_a, text_b)
        prompt = self._build_prompt(text_a, text_b)
        raw = self._call_llm(
            prompt, "gpt-4o-mini", api_key, "https://api.openai.com/v1/chat/completions"
        )
        return self._parse(raw) if raw else ("NEUTRAL", 0.0)

    def _classify_anthropic(self, text_a: str, text_b: str) -> Tuple[str, float]:
        api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
        if not api_key:
            log.warning("No Anthropic API key configured, falling back to lightweight")
            return LightweightClassifier().classify(text_a, text_b)
        prompt = self._build_prompt(text_a, text_b)
        try:
            import httpx

            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=15.0,
            )
            if resp.status_code == 200:
                raw = resp.json().get("content", [{}])[0].get("text", "").strip().upper()
                return self._parse(raw)
            log.warning("Anthropic call failed: %s %s", resp.status_code, resp.text)
        except Exception as e:
            log.warning("Anthropic call error: %s", e)
        return LightweightClassifier().classify(text_a, text_b)

    @staticmethod
    def _build_prompt(text_a: str, text_b: str) -> str:
        return (
            "Do these two statements contradict each other, support each other, or are they neutral?\n"
            "Respond with exactly one word: CONTRADICTION, ENTAILMENT, or NEUTRAL.\n\n"
            f'1: "{text_a}"\n'
            f'2: "{text_b}"'
        )

    @staticmethod
    def _parse(raw: str) -> Tuple[str, float]:
        for word in (CONTRADICTION, ENTAILMENT, NEUTRAL):
            if word in raw.upper():
                return word, 0.9 if word == CONTRADICTION else 0.7
        return "NEUTRAL", 0.0


class LocalNLClassifier(ContradictionClassifier):
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.CONTRADICTION_MODEL_PATH
        self._model = None
        self._load_model()

    def _load_model(self):
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
            log.info("Loaded NLI model: %s", self.model_name)
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for LocalNLClassifier. "
                "Install it with: pip install memory-thread[nli]"
            )
        except Exception as e:
            log.warning("Failed to load NLI model '%s': %s", self.model_name, e)
            raise

    def classify(self, text_a: str, text_b: str) -> Tuple[str, float]:
        if self._model is None:
            return "NEUTRAL", 0.0
        try:
            pairs = [(text_a, text_b)]
            scores = self._model.predict(pairs)[0]
            label_idx = int(scores.argmax())
            label = [ENTAILMENT, NEUTRAL, CONTRADICTION][label_idx]
            confidence = float(scores[label_idx])
            return label, confidence
        except Exception as e:
            log.warning("NLI classification failed: %s", e)
            return "NEUTRAL", 0.0


class LightweightClassifier(ContradictionClassifier):
    def classify(self, text_a: str, text_b: str) -> Tuple[str, float]:
        a_words = set(text_a.lower().split())
        b_words = set(text_b.lower().split())
        intersection = a_words & b_words
        union = a_words | b_words
        if not union:
            return "NEUTRAL", 0.0
        jaccard = len(intersection) / len(union)

        if jaccard < 0.1:
            return "NEUTRAL", 0.3

        antonym_hits = 0
        from memory_thread.services.meta_stability_service import ANTONYM_PAIRS

        for w1 in a_words:
            for w2 in b_words:
                if w1 == w2:
                    continue
                for antonym in ANTONYM_PAIRS.values():
                    if w2 == antonym:
                        antonym_hits += 1
                        break

        if antonym_hits > 0 and jaccard > 0.15:
            return "CONTRADICTION", min(0.5 + 0.1 * antonym_hits, 0.85)

        if any(w in a_words and w in b_words for w in {"likes", "prefers", "loves", "happy"}):
            return "ENTAILMENT", 0.4

        return "NEUTRAL", 0.2


def get_classifier(mode: Optional[str] = None) -> ContradictionClassifier:
    mode = (mode or settings.CONTRADICTION_MODE).lower()
    if mode == "api":
        return APIProviderClassifier()
    elif mode == "local":
        try:
            return LocalNLClassifier()
        except ImportError:
            log.warning("Local NLI unavailable, falling back to API provider")
            return APIProviderClassifier()
    elif mode == "lightweight":
        return LightweightClassifier()
    elif mode == "auto":
        try:
            return LocalNLClassifier()
        except (ImportError, Exception):
            key = getattr(settings, "OPENAI_API_KEY", None) or getattr(
                settings, "ANTHROPIC_API_KEY", None
            )
            if key:
                return APIProviderClassifier()
            return LightweightClassifier()
    else:
        log.warning("Unknown CONTRADICTION_MODE '%s', using lightweight", mode)
        return LightweightClassifier()
