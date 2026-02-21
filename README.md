# presidio-amplify

A **self-contained demo REST API** built with **AWS Amplify Gen 2** that exposes two public (no-auth) PII endpoints powered by [Microsoft Presidio](https://microsoft.github.io/presidio/) running inside AWS Lambda.

## Architecture

```
API Gateway (REST)
  └── POST /v1/pii/analyze    → Lambda (Python 3.11) → Presidio AnalyzerEngine
  └── POST /v1/pii/anonymize  → Lambda (Python 3.11) → Presidio AnonymizerEngine

Both Lambdas share a Lambda Layer containing:
  • presidio-analyzer  ≥ 2.2.356
  • presidio-anonymizer ≥ 2.2.356
  • spaCy 3.7.x
  • en_core_web_sm-3.7.1  (small English NLP model, ~12 MB)
  • fr_core_news_sm-3.7.0  (small French NLP model, ~16 MB)
```

> **NLP limitations (demo only):** The small spaCy models (`*_sm`) have lower
> recall than the medium/large variants. For production, swap to
> `en_core_web_lg` / `fr_dep_news_trf` and re-benchmark recall.
> The layer size is ~220–240 MB (within the 250 MB Lambda layer limit).

## Prerequisites

| Tool | Min version | Notes |
|------|-------------|-------|
| Node.js | 20 | `npm` |
| AWS CLI | 2 | configured with deploy credentials |
| Docker | any | required to build the Lambda Layer |
| Python | 3.11 | for running unit tests locally |

## Quick start

```bash
# Install Node dependencies
npm install

# (Optional) run unit tests – no Docker / AWS needed
pip install pytest
pytest

# Deploy to your AWS sandbox
npx ampx sandbox
```

After deployment the CDK output will print the `PresidioApiUrl`.  
Test with:

```bash
BASE="https://<id>.execute-api.<region>.amazonaws.com/prod"

# Analyze
curl -s -X POST "$BASE/v1/pii/analyze" \
  -H "Content-Type: application/json" \
  -d '{"text":"My email is john@example.com and phone 555-1234"}' | jq .

# Anonymize
curl -s -X POST "$BASE/v1/pii/anonymize" \
  -H "Content-Type: application/json" \
  -d '{"text":"My email is john@example.com","operators":{"EMAIL_ADDRESS":{"type":"redact"}}}' | jq .
```

## Endpoint reference

### POST /v1/pii/analyze

**Request**

```json
{
  "text":           "<string, required>",
  "language":       "en",
  "entities":       ["EMAIL_ADDRESS", "PHONE_NUMBER"],
  "scoreThreshold": 0.5
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `text` | string | — | Text to analyse (**required**) |
| `language` | `"en"` \| `"fr"` | `"en"` | Language of the text |
| `entities` | string[] | all | Restrict to specific entity types |
| `scoreThreshold` | number 0–1 | `0.5` | Minimum confidence score |

**Response 200**

```json
{
  "requestId": "uuid",
  "result": {
    "entities": [
      { "entityType": "EMAIL_ADDRESS", "start": 11, "end": 27, "score": 0.85 }
    ],
    "summary": {
      "countsByType": { "EMAIL_ADDRESS": 1 }
    }
  }
}
```

---

### POST /v1/pii/anonymize

**Request**

```json
{
  "text":           "<string, required>",
  "language":       "en",
  "entities":       ["EMAIL_ADDRESS"],
  "scoreThreshold": 0.5,
  "operators": {
    "EMAIL_ADDRESS": { "type": "replace" },
    "PHONE_NUMBER":  { "type": "mask", "params": { "masking_char": "*", "chars_to_mask": 4, "from_end": true } }
  }
}
```

Supported operator types:

| Type | Description |
|------|-------------|
| `replace` | Replace with `<ENTITY_TYPE>` placeholder (default) |
| `redact` | Delete the span entirely |
| `mask` | Replace characters with a mask character |
| `hash` | SHA-256 / SHA-512 hash of the value |
| `encrypt` | AES-CBC encryption (requires `"key"` param, base64, 128/192/256-bit) |

**Response 200**

```json
{
  "requestId": "uuid",
  "result": {
    "anonymizedText": "My email is <EMAIL_ADDRESS>",
    "entities": [
      { "entityType": "EMAIL_ADDRESS", "start": 12, "end": 26, "operatorName": "replace" }
    ]
  }
}
```

---

## Security notes

* Both endpoints are **public** (no authentication) — intended for demo/testing only.
* The raw request body is **never logged** to prevent accidental PII exposure in CloudWatch logs.
* Only request metadata (language, flag for entities/operators) is logged.
* For production: add API Gateway authorizers, WAF, request throttling, and access logging to a separate log group.

## Running unit tests

```bash
pip install pytest
pytest -v
```

Tests mock all Presidio/spaCy calls and run without any AWS credentials or Docker.

## Deploying to production (CI/CD)

```bash
# Set up Amplify pipeline, then run:
npx ampx pipeline-deploy --branch main --app-id <amplify-app-id>
```

Docker must be available in the build environment to bundle the Lambda Layer.
