"""
Unit tests for amplify/functions/pii-anonymize/index.py

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
# Bootstrap minimal Presidio stubs
# ---------------------------------------------------------------------------

def _make_presidio_stubs():
    # presidio_analyzer
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

    # presidio_anonymizer
    pan = types.ModuleType("presidio_anonymizer")
    pan_entities = types.ModuleType("presidio_anonymizer.entities")

    class FakeAnonymizerResult:
        def __init__(self, text="", items=None):
            self.text = text
            self.items = items or []

    class FakeAnonymizerEngine:
        def __init__(self, **kwargs):
            pass

        def anonymize(self, *, text, analyzer_results, operators=None):
            return FakeAnonymizerResult(text=text, items=[])

    class FakeOperatorConfig:
        def __init__(self, operator_name, params=None):
            self.operator_name = operator_name
            self.params = params or {}

    pan.AnonymizerEngine = FakeAnonymizerEngine
    pan_entities.OperatorConfig = FakeOperatorConfig

    sys.modules.setdefault("presidio_analyzer", pa)
    sys.modules.setdefault("presidio_analyzer.nlp_engine", pa_nlp)
    sys.modules.setdefault("presidio_anonymizer", pan)
    sys.modules.setdefault("presidio_anonymizer.entities", pan_entities)

    return FakeAnonymizerResult, FakeOperatorConfig


_FakeAnonymizerResult, _FakeOperatorConfig = _make_presidio_stubs()

# Import the handler by file path to avoid sys.modules collisions with the
# analyze handler (both files are named index.py).
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "pii_anonymize",
    "amplify/functions/pii-anonymize/index.py",
)
anonymize_module = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(anonymize_module)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(body: dict | None = None, raw_body: str | None = None):
    if raw_body is None:
        raw_body = json.dumps(body) if body is not None else None
    event = {"body": raw_body}
    return anonymize_module.handler(event, {})


def _json(response: dict) -> dict:
    return json.loads(response["body"])


def _make_anon_result(text="anonymised", items=None):
    return _FakeAnonymizerResult(text=text, items=items or [])


def _make_anon_item(entity_type, start, end, operator="replace"):
    item = MagicMock()
    item.entity_type = entity_type
    item.start = start
    item.end = end
    item.operator = operator
    return item


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestAnonymizeValidation:
    def test_missing_text_returns_400(self):
        resp = _call({})
        assert resp["statusCode"] == 400
        assert "text" in _json(resp)["error"]

    def test_empty_text_returns_400(self):
        resp = _call({"text": ""})
        assert resp["statusCode"] == 400

    def test_text_not_string_returns_400(self):
        resp = _call({"text": 123})
        assert resp["statusCode"] == 400

    def test_invalid_language_returns_400(self):
        resp = _call({"text": "hello", "language": "es"})
        assert resp["statusCode"] == 400

    def test_invalid_score_threshold_returns_400(self):
        resp = _call({"text": "hello", "scoreThreshold": "abc"})
        assert resp["statusCode"] == 400

    def test_score_threshold_out_of_range_returns_400(self):
        resp = _call({"text": "hello", "scoreThreshold": -0.1})
        assert resp["statusCode"] == 400

    def test_entities_not_list_returns_400(self):
        resp = _call({"text": "hello", "entities": "EMAIL_ADDRESS"})
        assert resp["statusCode"] == 400

    def test_operators_not_dict_returns_400(self):
        resp = _call({"text": "hello", "operators": "replace"})
        assert resp["statusCode"] == 400

    def test_operator_value_not_dict_returns_400(self):
        resp = _call({"text": "hello", "operators": {"EMAIL_ADDRESS": "replace"}})
        assert resp["statusCode"] == 400

    def test_invalid_json_body_returns_400(self):
        resp = _call(raw_body="{invalid}")
        assert resp["statusCode"] == 400

    def test_null_body_returns_400(self):
        resp = _call(raw_body=None)
        assert resp["statusCode"] == 400


# ---------------------------------------------------------------------------
# Success path tests
# ---------------------------------------------------------------------------

class TestAnonymizeSuccess:
    def setup_method(self):
        anonymize_module._analyzer = None
        anonymize_module._anonymizer = None

    def test_returns_200_with_request_id(self):
        with patch.object(anonymize_module, "_get_engines") as mock_engines:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = []
            mock_anonymizer = MagicMock()
            mock_anonymizer.anonymize.return_value = _make_anon_result("hello")
            mock_engines.return_value = mock_analyzer, mock_anonymizer

            resp = _call({"text": "hello world"})

        assert resp["statusCode"] == 200
        body = _json(resp)
        assert "requestId" in body
        uuid.UUID(body["requestId"])

    def test_anonymized_text_in_response(self):
        with patch.object(anonymize_module, "_get_engines") as mock_engines:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = []
            mock_anonymizer = MagicMock()
            mock_anonymizer.anonymize.return_value = _make_anon_result(
                "<EMAIL_ADDRESS> called me"
            )
            mock_engines.return_value = mock_analyzer, mock_anonymizer

            resp = _call({"text": "john@example.com called me"})

        body = _json(resp)
        assert body["result"]["anonymizedText"] == "<EMAIL_ADDRESS> called me"

    def test_entities_in_response(self):
        item = _make_anon_item("EMAIL_ADDRESS", 0, 20, "replace")

        with patch.object(anonymize_module, "_get_engines") as mock_engines:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = []
            mock_anonymizer = MagicMock()
            mock_anonymizer.anonymize.return_value = _make_anon_result(
                "<EMAIL_ADDRESS>", items=[item]
            )
            mock_engines.return_value = mock_analyzer, mock_anonymizer

            resp = _call({"text": "test@example.com here"})

        entities = _json(resp)["result"]["entities"]
        assert entities == [
            {
                "entityType": "EMAIL_ADDRESS",
                "start": 0,
                "end": 20,
                "operatorName": "replace",
            }
        ]

    def test_default_language_is_en(self):
        with patch.object(anonymize_module, "_get_engines") as mock_engines:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = []
            mock_anonymizer = MagicMock()
            mock_anonymizer.anonymize.return_value = _make_anon_result()
            mock_engines.return_value = mock_analyzer, mock_anonymizer

            _call({"text": "hello"})
            call_kwargs = mock_analyzer.analyze.call_args.kwargs
            assert call_kwargs["language"] == "en"

    def test_french_language_accepted(self):
        with patch.object(anonymize_module, "_get_engines") as mock_engines:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = []
            mock_anonymizer = MagicMock()
            mock_anonymizer.anonymize.return_value = _make_anon_result()
            mock_engines.return_value = mock_analyzer, mock_anonymizer

            resp = _call({"text": "Bonjour", "language": "fr"})

        assert resp["statusCode"] == 200

    def test_operators_passed_to_anonymizer(self):
        with patch.object(anonymize_module, "_get_engines") as mock_engines:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = []
            mock_anonymizer = MagicMock()
            mock_anonymizer.anonymize.return_value = _make_anon_result()
            mock_engines.return_value = mock_analyzer, mock_anonymizer

            _call({
                "text": "hello",
                "operators": {
                    "EMAIL_ADDRESS": {"type": "redact", "params": {}}
                },
            })

            _, call_kwargs = mock_anonymizer.anonymize.call_args
            assert call_kwargs["operators"] is not None

    def test_null_operators_omitted(self):
        """When no operators are specified, None is passed to anonymizer."""
        with patch.object(anonymize_module, "_get_engines") as mock_engines:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = []
            mock_anonymizer = MagicMock()
            mock_anonymizer.anonymize.return_value = _make_anon_result()
            mock_engines.return_value = mock_analyzer, mock_anonymizer

            _call({"text": "hello"})
            _, call_kwargs = mock_anonymizer.anonymize.call_args
            assert call_kwargs["operators"] is None

    def test_content_type_is_json(self):
        with patch.object(anonymize_module, "_get_engines") as mock_engines:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = []
            mock_anonymizer = MagicMock()
            mock_anonymizer.anonymize.return_value = _make_anon_result()
            mock_engines.return_value = mock_analyzer, mock_anonymizer

            resp = _call({"text": "hello"})

        assert resp["headers"]["Content-Type"] == "application/json"

    def test_presidio_error_returns_500(self):
        with patch.object(anonymize_module, "_get_engines") as mock_engines:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.side_effect = RuntimeError("crash")
            mock_anonymizer = MagicMock()
            mock_engines.return_value = mock_analyzer, mock_anonymizer

            resp = _call({"text": "hello"})

        assert resp["statusCode"] == 500
