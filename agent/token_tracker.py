import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger("docker_token_logger")

STORAGE_PATH = Path(".token_usage.json")


class TokenTracker:
    def __init__(self, token_limit: int = 100000):
        self.token_limit = token_limit
        self.total_tokens: int = 0
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.key_stats: dict[str, dict[str, int]] = {}
        self._load_from_storage()

    def _load_from_storage(self) -> None:
        if STORAGE_PATH.exists():
            try:
                data = json.loads(STORAGE_PATH.read_text(encoding="utf-8"))
                self.total_tokens = data.get("total_tokens", 0)
                self.total_prompt_tokens = data.get("total_prompt_tokens", 0)
                self.total_completion_tokens = data.get("total_completion_tokens", 0)
                self.key_stats = data.get("key_stats", {})
            except Exception as e:
                logger.warning("No se pudo cargar .token_usage.json: %s", e)

    def _save_to_storage(self) -> None:
        try:
            data = {
                "total_tokens": self.total_tokens,
                "total_prompt_tokens": self.total_prompt_tokens,
                "total_completion_tokens": self.total_completion_tokens,
                "key_stats": self.key_stats,
            }
            STORAGE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("No se pudo guardar .token_usage.json: %s", e)

    def set_token_limit(self, limit: int) -> None:
        if limit > 0:
            self.token_limit = limit

    def record_usage(
        self,
        key_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> None:
        if total_tokens <= 0:
            total_tokens = prompt_tokens + completion_tokens

        self.total_tokens += total_tokens
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens

        if key_name not in self.key_stats:
            self.key_stats[key_name] = {
                "total": 0,
                "prompt": 0,
                "completion": 0,
                "calls": 0,
            }

        self.key_stats[key_name]["total"] += total_tokens
        self.key_stats[key_name]["prompt"] += prompt_tokens
        self.key_stats[key_name]["completion"] += completion_tokens
        self.key_stats[key_name]["calls"] += 1

        self._save_to_storage()

        pct = (self.total_tokens / self.token_limit * 100) if self.token_limit > 0 else 0.0

        # Formato de log claro para Docker
        logger.info(
            "🔑 [API KEY EN USO: %s] | Tokens esta llamada: %d (Prompt: %d, Completion: %d) | Acumulado total: %d/%d (%.1f%%)",
            key_name,
            total_tokens,
            prompt_tokens,
            completion_tokens,
            self.total_tokens,
            self.token_limit,
            pct,
        )

    def log_turn_summary(
        self,
        turn_prompt: int,
        turn_completion: int,
        turn_total: int,
        keys_used: list[str],
    ) -> None:
        keys_str = ", ".join(set(keys_used)) if keys_used else "Desconocida"
        pct = (self.total_tokens / self.token_limit * 100) if self.token_limit > 0 else 0.0
        logger.info(
            "📊 [RESUMEN PREGUNTA] API Keys: [%s] | Total tokens pregunta: %d (Prompt: %d, Completion: %d) | Acumulado global: %d/%d (%.1f%%)",
            keys_str,
            turn_total,
            turn_prompt,
            turn_completion,
            self.total_tokens,
            self.token_limit,
            pct,
        )

    def get_summary(self) -> dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "token_limit": self.token_limit,
            "usage_percentage": round(
                (self.total_tokens / self.token_limit * 100) if self.token_limit > 0 else 0, 2
            ),
            "key_stats": self.key_stats,
        }


token_tracker = TokenTracker()


class KeyTokenCallbackHandler(BaseCallbackHandler):
    """CallbackHandler para interceptar uso de tokens y asociarlo al nombre de la API Key usada."""

    def __init__(self, key_name: str, tracker: TokenTracker = token_tracker):
        super().__init__()
        self.key_name = key_name
        self.tracker = tracker

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        prompt = 0
        completion = 0
        total = 0

        # 1. Extraer desde response.llm_output
        if response.llm_output and isinstance(response.llm_output, dict):
            usage = response.llm_output.get("token_usage") or response.llm_output.get("usage")
            if usage and isinstance(usage, dict):
                prompt = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
                completion = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
                total = usage.get("total_tokens", 0) or (prompt + completion)

        # 2. Extraer desde generations si no estuvo en llm_output
        if total == 0 and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    msg = getattr(gen, "message", None)
                    if msg:
                        usage_meta = getattr(msg, "usage_metadata", None)
                        if usage_meta and isinstance(usage_meta, dict):
                            p = usage_meta.get("input_tokens", 0)
                            c = usage_meta.get("output_tokens", 0)
                            t = usage_meta.get("total_tokens", 0) or (p + c)
                            if t > 0:
                                prompt += p
                                completion += c
                                total += t

                        resp_meta = getattr(msg, "response_metadata", None)
                        if resp_meta and isinstance(resp_meta, dict):
                            tu = resp_meta.get("token_usage") or resp_meta.get("usage")
                            if tu and isinstance(tu, dict):
                                p = tu.get("prompt_tokens", 0) or tu.get("input_tokens", 0)
                                c = tu.get("completion_tokens", 0) or tu.get("output_tokens", 0)
                                t = tu.get("total_tokens", 0) or (p + c)
                                if t > 0 and total == 0:
                                    prompt += p
                                    completion += c
                                    total += t

        if total == 0 and (prompt > 0 or completion > 0):
            total = prompt + completion

        if total > 0 or prompt > 0 or completion > 0:
            self.tracker.record_usage(
                key_name=self.key_name,
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
            )
