"""
POST /v1/pii/anonymize

Anonymizes PII entities in the supplied text using Microsoft Presidio.

Request JSON:
    {
        "text":           <string, required>,
        "language":       "en"  (optional, default "en"),
        "entities":       ["EMAIL_ADDRESS", ...]  (optional, default all),
        "scoreThreshold": <number 0-1>  (optional, default 0.5),
        "operators":      {                        (optional)
            "<ENTITY_TYPE>": {
                "type":   "replace" | "redact" | "mask" | "hash" | "encrypt",
                "params": { ... }                  (operator-specific params)
            }
        }
    }

Response JSON (200):
    {
        "requestId": "<uuid>",
        "result": {
            "anonymizedText": "<string>",
            "entities": [
                {
                    "entityType":    "EMAIL_ADDRESS",
                    "start":         0,
                    "end":           15,
                    "operatorName":  "replace"
                }
            ]
        }
    }

Supported operators (Presidio defaults):
    replace  – replace with <ENTITY_TYPE> placeholder  (default)
    redact   – delete the span
    mask     – replace characters with a mask character
    hash     – SHA-256 / SHA-512 hash of the value
    encrypt  – AES-CBC encryption (requires "key" param, base64-encoded 128/192/256-bit)

Important: the raw request body is NEVER logged to avoid accidental PII exposure.
"""

import json
import logging
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Module-level singletons – initialised lazily to reduce cold-start latency
_analyzer = None
_anonymizer = None


def _get_engines():
    """Return (and lazily initialise) AnalyzerEngine + AnonymizerEngine."""
    global _analyzer, _anonymizer

    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        configuration = {
            "nlp_engine_name": "spacy",
            "models": [
                {"lang_code": "en", "model_name": "en_core_web_sm"},
            ],
        }
        provider = NlpEngineProvider(nlp_configuration=configuration)
        nlp_engine = provider.create_engine()
        _analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine,
            supported_languages=["en"],
        )
        logger.info("AnalyzerEngine initialised")

    if _anonymizer is None:
        from presidio_anonymizer import AnonymizerEngine

        _anonymizer = AnonymizerEngine()
        logger.info("AnonymizerEngine initialised")

    return _analyzer, _anonymizer


def handler(event, context):  # noqa: ARG001
    # ── Parse body ────────────────────────────────────────────────────────────
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _error(400, "Invalid JSON body")

    # ── Validate inputs (log schema shape, never log values) ─────────────────
    text = body.get("text")
    if not text or not isinstance(text, str):
        return _error(400, '"text" is required and must be a non-empty string')

    language = body.get("language", "en")
    if language != "en":
        return _error(400, '"language" must be "en"')

    entities = body.get("entities")
    if entities is not None:
        if not isinstance(entities, list) or not all(
            isinstance(e, str) for e in entities
        ):
            return _error(400, '"entities" must be a list of strings')
        entities = entities or None  # treat empty list as "all entities"

    score_threshold = body.get("scoreThreshold", 0.5)
    try:
        score_threshold = float(score_threshold)
        if not 0.0 <= score_threshold <= 1.0:
            raise ValueError
    except (TypeError, ValueError):
        return _error(400, '"scoreThreshold" must be a number between 0 and 1')

    operators_raw = body.get("operators") or {}
    if not isinstance(operators_raw, dict):
        return _error(400, '"operators" must be an object')

    # ── Log metadata only – never the text ───────────────────────────────────
    logger.info(
        "anonymize request",
        extra={
            "language": language,
            "hasEntities": bool(entities),
            "scoreThreshold": score_threshold,
            "hasOperators": bool(operators_raw),
        },
    )

    # ── Build operator configs ────────────────────────────────────────────────
    operator_configs = {}
    if operators_raw:
        try:
            from presidio_anonymizer.entities import OperatorConfig

            for entity_type, op in operators_raw.items():
                if not isinstance(op, dict):
                    return _error(
                        400, f'"operators.{entity_type}" must be an object'
                    )
                op_type = op.get("type", "replace")
                op_params = op.get("params", {})
                operator_configs[entity_type] = OperatorConfig(
                    op_type, op_params
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Invalid operator config: %s", type(exc).__name__)
            return _error(400, "Invalid operator configuration")

    # ── Run analysis + anonymization ──────────────────────────────────────────
    try:
        analyzer, anonymizer = _get_engines()

        analyzer_results = analyzer.analyze(
            text=text,
            language=language,
            entities=entities if entities else None,
            score_threshold=score_threshold,
        )

        anon_result = anonymizer.anonymize(
            text=text,
            analyzer_results=analyzer_results,
            operators=operator_configs if operator_configs else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Presidio error: %s", type(exc).__name__)
        return _error(500, "Anonymization failed")

    # ── Build response ────────────────────────────────────────────────────────
    entities_out = [
        {
            "entityType": item.entity_type,
            "start": item.start,
            "end": item.end,
            "operatorName": item.operator,
        }
        for item in anon_result.items
    ]

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "requestId": str(uuid.uuid4()),
                "result": {
                    "anonymizedText": anon_result.text,
                    "entities": entities_out,
                },
            }
        ),
    }


def _error(status: int, message: str) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message}),
    }
