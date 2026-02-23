import { useState } from 'react';
import {
  AppShell,
  Button,
  Checkbox,
  Container,
  Group,
  MultiSelect,
  NumberInput,
  Select,
  Slider,
  Stack,
  Tabs,
  Text,
  Textarea,
  TextInput,
  Title,
  Badge,
  Table,
  Alert,
  Paper,
  Divider,
  Box,
} from '@mantine/core';
import outputs from '../../amplify_outputs.json';

// Type for Amplify outputs with custom API configuration
interface AmplifyOutputs {
  custom?: {
    API?: {
      PresidioApi?: {
        endpoint?: string;
        region?: string;
      };
    };
  };
}

// Get API base URL from Amplify outputs (deployed) or environment variable (local dev)
const API_BASE_URL = (outputs as AmplifyOutputs).custom?.API?.PresidioApi?.endpoint ?? import.meta.env.VITE_API_BASE_URL ?? '';

// Default value to effectively mask all characters in a field
const DEFAULT_CHARS_TO_MASK = 999;

const ENTITY_OPTIONS = [
  'PERSON', 'LOCATION', 'ORGANIZATION', 'EMAIL_ADDRESS', 'PHONE_NUMBER',
  'CREDIT_CARD', 'IBAN_CODE', 'IP_ADDRESS', 'DATE_TIME', 'NRP',
  'MEDICAL_LICENSE', 'URL', 'US_SSN', 'US_BANK_NUMBER', 'US_DRIVER_LICENSE',
  'US_PASSPORT', 'US_ITIN',
];

interface AnalyzeEntity {
  entityType: string;
  start: number;
  end: number;
  score: number;
}

interface AnalyzeResult {
  status: 'success' | 'error';
  duration: number;
  data?: AnalyzeEntity[];
  error?: string;
  raw?: unknown;
}

interface AnonymizeResult {
  status: 'success' | 'error';
  duration: number;
  text?: string;
  error?: string;
  raw?: unknown;
}

export default function App() {
  // Shared state
  const [inputText, setInputText] = useState('');
  const [language, setLanguage] = useState<string>('en');
  const [scoreThreshold, setScoreThreshold] = useState(0.5);
  const [entities, setEntities] = useState<string[]>([]);

  // Analyze state
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeResult | null>(null);
  const [analyzeLoading, setAnalyzeLoading] = useState(false);

  // Anonymize state
  const [operator, setOperator] = useState<string>('redact');
  const [maskingChar, setMaskingChar] = useState('*');
  const [charsToMask, setCharsToMask] = useState<number | string>(DEFAULT_CHARS_TO_MASK);
  const [fromEnd, setFromEnd] = useState(false);
  const [newValue, setNewValue] = useState('<ANONYMIZED>');
  const [anonymizeResult, setAnonymizeResult] = useState<AnonymizeResult | null>(null);
  const [anonymizeLoading, setAnonymizeLoading] = useState(false);

  async function handleAnalyze() {
    setAnalyzeLoading(true);
    setAnalyzeResult(null);
    const t0 = Date.now();
    try {
      const body: Record<string, unknown> = {
        text: inputText,
        language,
        scoreThreshold,
      };
      if (entities.length > 0) body.entities = entities;

      const resp = await fetch(`${API_BASE_URL}/v1/pii/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const duration = Date.now() - t0;
      const data = await resp.json();
      if (!resp.ok) {
        setAnalyzeResult({ status: 'error', duration, error: JSON.stringify(data), raw: data });
      } else {
        setAnalyzeResult({ status: 'success', duration, data: data.result?.entities ?? [], raw: data });
      }
    } catch (err) {
      setAnalyzeResult({ status: 'error', duration: Date.now() - t0, error: String(err) });
    } finally {
      setAnalyzeLoading(false);
    }
  }

  async function handleAnonymize() {
    setAnonymizeLoading(true);
    setAnonymizeResult(null);
    const t0 = Date.now();
    try {
      // Build operator params based on selected operator type
      const operatorParams: Record<string, unknown> = {};
      if (operator === 'mask') {
        operatorParams.masking_char = maskingChar;
        operatorParams.chars_to_mask = typeof charsToMask === 'number' ? charsToMask : parseInt(String(charsToMask), 10);
        operatorParams.from_end = fromEnd;
      } else if (operator === 'replace') {
        operatorParams.new_value = newValue;
      }

      // Build operators object - apply to all entity types in the list, or DEFAULT for all
      const operators: Record<string, Record<string, unknown>> = {};
      const targetEntities = entities.length > 0 ? entities : ['DEFAULT'];
      
      for (const entityType of targetEntities) {
        operators[entityType] = {
          type: operator,
          ...(Object.keys(operatorParams).length > 0 ? { params: operatorParams } : {}),
        };
      }

      const body: Record<string, unknown> = {
        text: inputText,
        language,
        scoreThreshold,
        operators,
      };
      if (entities.length > 0) body.entities = entities;

      const resp = await fetch(`${API_BASE_URL}/v1/pii/anonymize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const duration = Date.now() - t0;
      const data = await resp.json();
      if (!resp.ok) {
        setAnonymizeResult({ status: 'error', duration, error: JSON.stringify(data), raw: data });
      } else {
        setAnonymizeResult({
          status: 'success',
          duration,
          text: data.result?.anonymizedText ?? '',
          raw: data,
        });
      }
    } catch (err) {
      setAnonymizeResult({ status: 'error', duration: Date.now() - t0, error: String(err) });
    } finally {
      setAnonymizeLoading(false);
    }
  }

  const sharedInputs = (
    <Stack gap="sm">
      <Textarea
        label="Input text"
        placeholder="Paste text containing PII here..."
        minRows={4}
        autosize
        value={inputText}
        onChange={(e) => setInputText(e.currentTarget.value)}
      />
      <Group grow>
        <Select
          label="Language"
          data={[{ value: 'en', label: 'English (en)' }, { value: 'fr', label: 'French (fr)' }]}
          value={language}
          onChange={(v) => setLanguage(v ?? 'en')}
        />
        <Box>
          <Text size="sm" fw={500} mb={4}>Score threshold: {scoreThreshold.toFixed(2)}</Text>
          <Slider
            min={0}
            max={1}
            step={0.05}
            value={scoreThreshold}
            onChange={setScoreThreshold}
            marks={[
              { value: 0, label: '0' },
              { value: 0.5, label: '0.5' },
              { value: 1, label: '1' },
            ]}
          />
        </Box>
      </Group>
      <MultiSelect
        label="Entities (leave empty for all)"
        placeholder="Select entities to detect..."
        data={ENTITY_OPTIONS}
        value={entities}
        onChange={setEntities}
        searchable
        clearable
      />
    </Stack>
  );

  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <Container h="100%" style={{ display: 'flex', alignItems: 'center' }}>
          <Title order={3}>PII Demo (Presidio)</Title>
        </Container>
      </AppShell.Header>
      <AppShell.Main>
        <Container size="lg" py="md">
          <Tabs defaultValue="analyze">
            <Tabs.List>
              <Tabs.Tab value="analyze">Analyze</Tabs.Tab>
              <Tabs.Tab value="anonymize">Anonymize</Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="analyze" pt="md">
              <Stack gap="md">
                {sharedInputs}
                <Button onClick={handleAnalyze} loading={analyzeLoading} disabled={!inputText.trim()}>
                  Send request
                </Button>
                {analyzeResult && (
                  <Paper withBorder p="md">
                    <Stack gap="sm">
                      <Group>
                        <Badge color={analyzeResult.status === 'success' ? 'green' : 'red'}>
                          {analyzeResult.status}
                        </Badge>
                        <Text size="sm" c="dimmed">{analyzeResult.duration}ms</Text>
                      </Group>
                      {analyzeResult.status === 'error' && (
                        <Alert color="red" title="Error">{analyzeResult.error}</Alert>
                      )}
                      {analyzeResult.status === 'success' && analyzeResult.data && analyzeResult.data.length > 0 && (
                        <>
                          <Text fw={500}>Detected entities ({analyzeResult.data.length})</Text>
                          <Table striped withTableBorder>
                            <Table.Thead>
                              <Table.Tr>
                                <Table.Th>Type</Table.Th>
                                <Table.Th>Detected Text</Table.Th>
                                <Table.Th>Position</Table.Th>
                                <Table.Th>Score</Table.Th>
                              </Table.Tr>
                            </Table.Thead>
                            <Table.Tbody>
                              {analyzeResult.data.map((e, i) => (
                                <Table.Tr key={i}>
                                  <Table.Td><Badge variant="light">{e.entityType}</Badge></Table.Td>
                                  <Table.Td><Text ff="monospace" size="sm">{inputText.substring(e.start, e.end)}</Text></Table.Td>
                                  <Table.Td><Text size="xs" c="dimmed">{e.start}-{e.end}</Text></Table.Td>
                                  <Table.Td>{e.score?.toFixed(3)}</Table.Td>
                                </Table.Tr>
                              ))}
                            </Table.Tbody>
                          </Table>
                        </>
                      )}
                      {analyzeResult.status === 'success' && analyzeResult.data?.length === 0 && (
                        <Text c="dimmed">No entities detected.</Text>
                      )}
                      <Divider />
                      <Text fw={500} size="sm">Response JSON</Text>
                      <pre style={{ background: '#f5f5f5', padding: '12px', borderRadius: '4px', overflow: 'auto', fontSize: '12px' }}>
                        {JSON.stringify(analyzeResult.raw, null, 2)}
                      </pre>
                    </Stack>
                  </Paper>
                )}
              </Stack>
            </Tabs.Panel>

            <Tabs.Panel value="anonymize" pt="md">
              <Stack gap="md">
                {sharedInputs}
                <Select
                  label="Operator"
                  data={[
                    { value: 'redact', label: 'Redact' },
                    { value: 'mask', label: 'Mask' },
                    { value: 'replace', label: 'Replace' },
                  ]}
                  value={operator}
                  onChange={(v) => setOperator(v ?? 'redact')}
                />
                {operator === 'mask' && (
                  <Stack gap="sm">
                    <TextInput
                      label="Masking character"
                      value={maskingChar}
                      onChange={(e) => setMaskingChar(e.currentTarget.value.slice(0, 1) || '*')}
                      maxLength={1}
                      style={{ maxWidth: 160 }}
                    />
                    <NumberInput
                      label="Characters to mask"
                      value={charsToMask}
                      onChange={setCharsToMask}
                      min={1}
                      style={{ maxWidth: 200 }}
                    />
                    <Checkbox
                      label="From end"
                      checked={fromEnd}
                      onChange={(e) => setFromEnd(e.currentTarget.checked)}
                    />
                  </Stack>
                )}
                {operator === 'replace' && (
                  <TextInput
                    label="Replacement value"
                    value={newValue}
                    onChange={(e) => setNewValue(e.currentTarget.value)}
                    style={{ maxWidth: 300 }}
                  />
                )}
                <Button onClick={handleAnonymize} loading={anonymizeLoading} disabled={!inputText.trim()}>
                  Send request
                </Button>
                {anonymizeResult && (
                  <Paper withBorder p="md">
                    <Stack gap="sm">
                      <Group>
                        <Badge color={anonymizeResult.status === 'success' ? 'green' : 'red'}>
                          {anonymizeResult.status}
                        </Badge>
                        <Text size="sm" c="dimmed">{anonymizeResult.duration}ms</Text>
                      </Group>
                      {anonymizeResult.status === 'error' && (
                        <Alert color="red" title="Error">{anonymizeResult.error}</Alert>
                      )}
                      {anonymizeResult.status === 'success' && anonymizeResult.text !== undefined && (
                        <>
                          <Text fw={500}>Anonymized text</Text>
                          <Textarea value={anonymizeResult.text} readOnly autosize minRows={2} />
                        </>
                      )}
                      <Divider />
                      <Text fw={500} size="sm">Response JSON</Text>
                      <pre style={{ background: '#f5f5f5', padding: '12px', borderRadius: '4px', overflow: 'auto', fontSize: '12px' }}>
                        {JSON.stringify(anonymizeResult.raw, null, 2)}
                      </pre>
                    </Stack>
                  </Paper>
                )}
              </Stack>
            </Tabs.Panel>
          </Tabs>
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
