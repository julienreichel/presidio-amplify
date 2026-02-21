import * as path from "path";
import { fileURLToPath } from "url";
import { defineBackend } from "@aws-amplify/backend";
import * as cdk from "aws-cdk-lib";
import * as apigw from "aws-cdk-lib/aws-apigateway";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { PythonFunction, PythonLayerVersion } from "@aws-cdk/aws-lambda-python-alpha";

// ESM-compatible __dirname
const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Amplify Gen 2 backend.
 * No built-in Amplify categories are used; all resources are custom CDK.
 */
const backend = defineBackend({});

// ─── Custom CDK stack ────────────────────────────────────────────────────────

const apiStack = backend.createStack("PresidioApiStack");

// ─── Shared Lambda Layer: Presidio + spaCy + language models ─────────────────
//
// NOTE: Building this layer requires Docker (used by @aws-cdk/aws-lambda-python-alpha
// to run `pip install` in a Lambda-compatible container). Make sure Docker is
// available when running `ampx sandbox` or `cdk deploy`.
//
// Layer size: ~220–240 MB unzipped (spaCy + models dominate).
// Stays within the 250 MB Lambda layer limit.

const presidioLayer = new PythonLayerVersion(apiStack, "PresidioLayer", {
  entry: path.join(__dirname, "layer/presidio"),
  compatibleRuntimes: [lambda.Runtime.PYTHON_3_11],
  description:
    "presidio-analyzer, presidio-anonymizer, spaCy 3.7 + en/fr models",
});

// ─── Common Lambda settings ───────────────────────────────────────────────────

const lambdaDefaults = {
  runtime: lambda.Runtime.PYTHON_3_11,
  layers: [presidioLayer],
  timeout: cdk.Duration.seconds(30),
  // 1 GB RAM recommended: spaCy model loading is memory-intensive
  memorySize: 1024,
  environment: {
    PYTHONPATH: "/opt/python",
    // Avoid writing spaCy data to /tmp (read-only in layer); force home to /tmp
    HOME: "/tmp",
  },
};

// ─── POST /v1/pii/analyze ─────────────────────────────────────────────────────

const analyzeFunction = new PythonFunction(
  apiStack,
  "PiiAnalyzeFunction",
  {
    ...lambdaDefaults,
    entry: path.join(__dirname, "functions/pii-analyze"),
    index: "index.py",
    handler: "handler",
    description: "Detect PII entities in text using Microsoft Presidio",
  },
);

// ─── POST /v1/pii/anonymize ───────────────────────────────────────────────────

const anonymizeFunction = new PythonFunction(
  apiStack,
  "PiiAnonymizeFunction",
  {
    ...lambdaDefaults,
    entry: path.join(__dirname, "functions/pii-anonymize"),
    index: "index.py",
    handler: "handler",
    description: "Anonymize PII entities in text using Microsoft Presidio",
  },
);

// ─── REST API (no auth – demo only) ──────────────────────────────────────────

const api = new apigw.RestApi(apiStack, "PresidioRestApi", {
  restApiName: "presidio-pii-api",
  description: "Demo Presidio PII analyze / anonymize REST API",
  defaultCorsPreflightOptions: {
    allowOrigins: apigw.Cors.ALL_ORIGINS,
    allowMethods: ["POST", "OPTIONS"],
    allowHeaders: ["Content-Type"],
  },
  deployOptions: {
    stageName: "prod",
  },
});

const v1 = api.root.addResource("v1");
const pii = v1.addResource("pii");

// POST /v1/pii/analyze
pii
  .addResource("analyze")
  .addMethod(
    "POST",
    new apigw.LambdaIntegration(analyzeFunction, { proxy: true }),
  );

// POST /v1/pii/anonymize
pii
  .addResource("anonymize")
  .addMethod(
    "POST",
    new apigw.LambdaIntegration(anonymizeFunction, { proxy: true }),
  );

// ─── Stack outputs ────────────────────────────────────────────────────────────

new cdk.CfnOutput(apiStack, "PresidioApiUrl", {
  value: api.url,
  description: "Base URL of the Presidio PII REST API",
  exportName: "PresidioApiUrl",
});
