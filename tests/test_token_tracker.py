from unittest.mock import MagicMock
from agent.token_tracker import KeyTokenCallbackHandler, TokenTracker
from config.settings import Settings


def test_get_groq_api_key_details(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY_1", "gsk_test1")
    monkeypatch.setenv("GROQ_API_KEY_2", "gsk_test2")
    monkeypatch.setenv("GROQ_API_KEY_3", "gsk_test3")

    s = Settings()
    details = s.get_groq_api_key_details()

    names = [d["name"] for d in details]
    assert "GROQ_API_KEY_1" in names
    assert "GROQ_API_KEY_2" in names
    assert "GROQ_API_KEY_3" in names

    keys = s.get_groq_api_keys()
    assert "gsk_test1" in keys
    assert "gsk_test2" in keys
    assert "gsk_test3" in keys


def test_token_tracker_record_usage(tmp_path, monkeypatch):
    test_storage = tmp_path / ".token_usage.json"
    monkeypatch.setattr("agent.token_tracker.STORAGE_PATH", test_storage)

    tracker = TokenTracker(token_limit=100000)
    tracker.record_usage("GROQ_API_KEY_3", prompt_tokens=500, completion_tokens=150, total_tokens=650)

    assert tracker.total_tokens == 650
    assert tracker.total_prompt_tokens == 500
    assert tracker.total_completion_tokens == 150
    assert tracker.key_stats["GROQ_API_KEY_3"]["total"] == 650
    assert tracker.key_stats["GROQ_API_KEY_3"]["calls"] == 1

    summary = tracker.get_summary()
    assert summary["total_tokens"] == 650
    assert summary["token_limit"] == 100000
    assert summary["usage_percentage"] == 0.65


def test_key_token_callback_handler():
    tracker = TokenTracker(token_limit=100000)
    handler = KeyTokenCallbackHandler(key_name="GROQ_API_KEY_3", tracker=tracker)

    mock_llm_result = MagicMock()
    mock_llm_result.llm_output = {
        "token_usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "total_tokens": 1200,
        }
    }
    mock_llm_result.generations = []

    handler.on_llm_end(mock_llm_result)

    assert tracker.total_tokens == 1200
    assert tracker.key_stats["GROQ_API_KEY_3"]["total"] == 1200
