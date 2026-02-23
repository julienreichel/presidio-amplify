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
// Layer size optimizations: excludes test files, docs, and unnecessary metadata

const presidioLayer = new PythonLayerVersion(apiStack, "PresidioLayer", {
  entry: path.join(__dirname, "layer/presidio"),
  compatibleRuntimes: [lambda.Runtime.PYTHON_3_11],
  description:
    "presidio-analyzer, presidio-anonymizer, spaCy 3.7 + en model",
  bundling: {
    environment: {
      PIP_NO_CACHE_DIR: "1",
      PIP_DISABLE_PIP_VERSION_CHECK: "1",
      PIP_NO_COMPILE: "1",
    },
    commandHooks: {
      afterBundling(inputDir: string, outputDir: string): string[] {
        return [
          // Remove test files and directories
          `find ${outputDir} -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true`,
          `find ${outputDir} -type d -name "test" -exec rm -rf {} + 2>/dev/null || true`,
          `find ${outputDir} -type d -name "testing" -exec rm -rf {} + 2>/dev/null || true`,
          // Remove __pycache__ and .pyc files
          `find ${outputDir} -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true`,
          `find ${outputDir} -type f -name "*.pyc" -delete 2>/dev/null || true`,
          `find ${outputDir} -type f -name "*.pyo" -delete 2>/dev/null || true`,
          // Remove .so debug symbols
          `find ${outputDir} -name "*.so" -exec strip {} \\; 2>/dev/null || true`,
          // Remove unnecessary metadata
          `find ${outputDir} -type d -name "*.dist-info" -exec sh -c 'cd "$1" && ls | grep -v -E "^(METADATA|top_level.txt)$" | xargs rm -rf' _ {} \\; 2>/dev/null || true`,
          `find ${outputDir} -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true`,
          // Remove docs and markdown files
          `find ${outputDir} -type f -name "*.md" -delete 2>/dev/null || true`,
          `find ${outputDir} -type f -name "*.rst" -delete 2>/dev/null || true`,
          `find ${outputDir} -type f -name "*.txt" ! -name "top_level.txt" -delete 2>/dev/null || true`,
          `find ${outputDir} -type d -name "docs" -exec rm -rf {} + 2>/dev/null || true`,
          // Remove examples and benchmarks
          `find ${outputDir} -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true`,
          `find ${outputDir} -type d -name "benchmarks" -exec rm -rf {} + 2>/dev/null || true`,
          // Show final size
          `echo "=== Final layer size ===" && du -sh ${outputDir}`,
        ];
      },
      beforeBundling(): string[] {
        return [];
      },
    },
  },
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
