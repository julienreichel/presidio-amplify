"""
POST /v1/pii/analyze

Detects PII entities in the supplied text using Microsoft Presidio.

Request JSON:
    {
        "text":           <string, required>,
        "language":       "en"  (optional, default "en"),
        "entities":       ["EMAIL_ADDRESS", ...]  (optional, default all),
        "scoreThreshold": <number 0-1>  (optional, default 0.5)
    }

Response JSON (200):
    {
        "requestId": "<uuid>",
        "result": {
            "entities": [
                { "entityType": "EMAIL_ADDRESS", "start": 0, "end": 5, "score": 0.85 }
            ],
            "summary": {
                "countsByType": { "EMAIL_ADDRESS": 1 }
            }
        }
    }

Important: the raw request body is NEVER logged to avoid accidental PII exposure.
"""

import json
import logging
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Module-level singletons – initialised lazily to reduce cold-start latency
_analyzer = None


def _get_analyzer():
    """Return (and lazily initialise) the AnalyzerEngine with EN spaCy model."""
    global _analyzer
    if _analyzer is None:
        # Import here so the module can be imported without Presidio installed
        # (useful during unit-testing with mocks).
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
    return _analyzer


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

    # ── Log metadata only – never the text ───────────────────────────────────
    logger.info(
        "analyze request",
        extra={
            "language": language,
            "hasEntities": bool(entities),
            "scoreThreshold": score_threshold,
        },
    )

    # ── Run analysis ──────────────────────────────────────────────────────────
    try:
        analyzer = _get_analyzer()
        results = analyzer.analyze(
            text=text,
            language=language,
            entities=entities if entities else None,
            score_threshold=score_threshold,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Presidio analyzer error: %s", type(exc).__name__)
        return _error(500, "Analysis failed")

    # ── Build response ────────────────────────────────────────────────────────
    entities_out = [
        {
            "entityType": r.entity_type,
            "start": r.start,
            "end": r.end,
            "score": round(r.score, 4),
        }
        for r in results
    ]

    counts_by_type: dict[str, int] = {}
    for ent in entities_out:
        t = ent["entityType"]
        counts_by_type[t] = counts_by_type.get(t, 0) + 1

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "requestId": str(uuid.uuid4()),
                "result": {
                    "entities": entities_out,
                    "summary": {"countsByType": counts_by_type},
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
