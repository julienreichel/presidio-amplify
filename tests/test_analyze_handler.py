"""
Unit tests for amplify/functions/pii-analyze/index.py

Presidio / spaCy are mocked so these tests run without
the full NLP stack installed.
"""

import json
import sys
import types
import uuid
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap minimal Presidio stubs so the module can be imported without the
# real libraries present in this environment.
# ---------------------------------------------------------------------------

def _make_presidio_stubs():
    # presidio_analyzer stub
    pa = types.ModuleType("presidio_analyzer")
    pa_nlp = types.ModuleType("presidio_analyzer.nlp_engine")

    class FakeNlpEngineProvider:
        def __init__(self, nlp_configuration=None):
            pass

        def create_engine(self):
            return MagicMock()

    class FakeAnalyzerEngine:
        def __init__(self, **kwargs):
            pass

        def analyze(self, *, text, language, entities=None, score_threshold=0.5):
            return []

    pa_nlp.NlpEngineProvider = FakeNlpEngineProvider
    pa.AnalyzerEngine = FakeAnalyzerEngine
    pa.nlp_engine = pa_nlp

    sys.modules.setdefault("presidio_analyzer", pa)
    sys.modules.setdefault("presidio_analyzer.nlp_engine", pa_nlp)


_make_presidio_stubs()

# Import the handler by file path to avoid sys.modules collisions with the
# anonymize handler (both files are named index.py).
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "pii_analyze",
    "amplify/functions/pii-analyze/index.py",
)
analyze_module = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(analyze_module)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(body: dict | None = None, raw_body: str | None = None):
    """Invoke the handler with a fake API-GW proxy event."""
    if raw_body is None:
        raw_body = json.dumps(body) if body is not None else None
    event = {"body": raw_body}
    return analyze_module.handler(event, {})


def _json(response: dict) -> dict:
    return json.loads(response["body"])


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestAnalyzeValidation:
    def test_missing_text_returns_400(self):
        resp = _call({})
        assert resp["statusCode"] == 400
        assert "text" in _json(resp)["error"]

    def test_text_not_string_returns_400(self):
        resp = _call({"text": 42})
        assert resp["statusCode"] == 400

    def test_empty_text_returns_400(self):
        resp = _call({"text": ""})
        assert resp["statusCode"] == 400

    def test_invalid_language_returns_400(self):
        resp = _call({"text": "hello", "language": "de"})
        assert resp["statusCode"] == 400
        assert "language" in _json(resp)["error"]

    def test_invalid_score_threshold_string_returns_400(self):
        resp = _call({"text": "hello", "scoreThreshold": "bad"})
        assert resp["statusCode"] == 400

    def test_score_threshold_out_of_range_returns_400(self):
        resp = _call({"text": "hello", "scoreThreshold": 1.5})
        assert resp["statusCode"] == 400

    def test_entities_not_list_returns_400(self):
        resp = _call({"text": "hello", "entities": "EMAIL_ADDRESS"})
        assert resp["statusCode"] == 400

    def test_entities_list_of_non_strings_returns_400(self):
        resp = _call({"text": "hello", "entities": [1, 2]})
        assert resp["statusCode"] == 400

    def test_invalid_json_body_returns_400(self):
        resp = _call(raw_body="not json")
        assert resp["statusCode"] == 400
        assert "JSON" in _json(resp)["error"]

    def test_null_body_returns_400(self):
        resp = _call(raw_body=None)
        assert resp["statusCode"] == 400


# ---------------------------------------------------------------------------
# Success path tests
# ---------------------------------------------------------------------------

class TestAnalyzeSuccess:
    def setup_method(self):
        # Reset singleton so each test gets a fresh engine mock
        analyze_module._analyzer = None

    def _fake_result(self, entity_type, start, end, score):
        r = MagicMock()
        r.entity_type = entity_type
        r.start = start
        r.end = end
        r.score = score
        return r

    def test_returns_200_with_request_id(self):
        with patch.object(
            analyze_module, "_get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = []
            resp = _call({"text": "hello world"})

        assert resp["statusCode"] == 200
        body = _json(resp)
        assert "requestId" in body
        # Validate requestId is a UUID
        uuid.UUID(body["requestId"])

    def test_entities_mapped_correctly(self):
        fake_result = self._fake_result("EMAIL_ADDRESS", 0, 19, 0.9876)

        with patch.object(analyze_module, "_get_analyzer") as mock_get:
            mock_get.return_value.analyze.return_value = [fake_result]
            resp = _call({"text": "test@example.com ok"})

        body = _json(resp)
        assert body["result"]["entities"] == [
            {"entityType": "EMAIL_ADDRESS", "start": 0, "end": 19, "score": 0.9876}
        ]
        assert body["result"]["summary"]["countsByType"] == {"EMAIL_ADDRESS": 1}

    def test_summary_counts_multiple_types(self):
        results = [
            self._fake_result("EMAIL_ADDRESS", 0, 10, 0.9),
            self._fake_result("EMAIL_ADDRESS", 20, 30, 0.85),
            self._fake_result("PHONE_NUMBER", 40, 50, 0.8),
        ]

        with patch.object(analyze_module, "_get_analyzer") as mock_get:
            mock_get.return_value.analyze.return_value = results
            resp = _call({"text": "some text"})

        counts = _json(resp)["result"]["summary"]["countsByType"]
        assert counts == {"EMAIL_ADDRESS": 2, "PHONE_NUMBER": 1}

    def test_score_rounded_to_4dp(self):
        fake_result = self._fake_result("EMAIL_ADDRESS", 0, 5, 0.123456789)

        with patch.object(analyze_module, "_get_analyzer") as mock_get:
            mock_get.return_value.analyze.return_value = [fake_result]
            resp = _call({"text": "hello"})

        score = _json(resp)["result"]["entities"][0]["score"]
        assert score == round(0.123456789, 4)

    def test_default_language_is_en(self):
        with patch.object(analyze_module, "_get_analyzer") as mock_get:
            mock_get.return_value.analyze.return_value = []
            _call({"text": "hello"})
            call_kwargs = mock_get.return_value.analyze.call_args.kwargs
            assert call_kwargs["language"] == "en"

    def test_default_score_threshold_is_0_5(self):
        with patch.object(analyze_module, "_get_analyzer") as mock_get:
            mock_get.return_value.analyze.return_value = []
            _call({"text": "hello"})
            call_kwargs = mock_get.return_value.analyze.call_args.kwargs
            assert call_kwargs["score_threshold"] == 0.5

    def test_content_type_is_json(self):
        with patch.object(analyze_module, "_get_analyzer") as mock_get:
            mock_get.return_value.analyze.return_value = []
            resp = _call({"text": "hello"})

        assert resp["headers"]["Content-Type"] == "application/json"

    def test_empty_entities_list_treated_as_all(self):
        """Empty entities list should be treated as "detect all"."""
        with patch.object(analyze_module, "_get_analyzer") as mock_get:
            mock_get.return_value.analyze.return_value = []
            _call({"text": "hello", "entities": []})
            call_kwargs = mock_get.return_value.analyze.call_args.kwargs
            assert call_kwargs["entities"] is None

    def test_presidio_error_returns_500(self):
        with patch.object(analyze_module, "_get_analyzer") as mock_get:
            mock_get.return_value.analyze.side_effect = RuntimeError("boom")
            resp = _call({"text": "hello"})

        assert resp["statusCode"] == 500
