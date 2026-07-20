const BASE = ''

async function request<T>(
  url: string,
  options?: RequestInit,
): Promise<{ data: T; latency: number }> {
  const start = performance.now()
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`HTTP ${res.status}: ${err}`)
  }
  const data = await res.json()
  return { data, latency: Math.round(performance.now() - start) }
}

export interface PIIScanResult {
  entity_type: string
  start: number
  end: number
  score: number
}

export interface AnonymizedItem {
  start: number
  end: number
  entity_type: string
  operator: string
}

export interface Mapping {
  id: number
  gliner_label: string
  presidio_label: string
  is_active: boolean
}

export async function scanText(
  content: string,
  engine: string,
  entities?: string[],
) {
  return request<{ text: string; results: PIIScanResult[] }>(`/scan/${engine}`, {
    method: 'POST',
    body: JSON.stringify({ content, entities }),
  })
}

export async function anonymizeText(text: string, results: PIIScanResult[]) {
  return request<{ anonymized_text: string; items: AnonymizedItem[] }>(
    '/anonymize',
    {
      method: 'POST',
      body: JSON.stringify({ text, results }),
    },
  )
}

export async function deanonymizeText(text: string) {
  return request<{ deanonymized_text: string }>('/deanonymize', {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
}

export interface GatewayResponse {
  original_prompt: string
  safe_prompt: string
  llm_response_raw: string
  final_response: string
  session_id: string
}

export async function chatWithLLM(
  content: string,
  session_id: string,
  entities?: string[],
) {
  return request<GatewayResponse>('/gateway/chat', {
    method: 'POST',
    body: JSON.stringify({ content, session_id, entities }),
  })
}

export async function fetchMappings() {
  return request<Mapping[]>('/mappings/', { method: 'GET' })
}

export async function createMapping(gliner_label: string) {
  return request<Mapping>('/mappings/', {
    method: 'POST',
    body: JSON.stringify({ gliner_label }),
  })
}

export async function updateMapping(
  id: number,
  data: { gliner_label?: string; is_active?: boolean },
) {
  return request<Mapping>(`/mappings/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function removeMapping(id: number) {
  return request<{ status: string; message: string }>(`/mappings/${id}`, {
    method: 'DELETE',
  })
}

export async function getGlobalScanner() {
  return request<{ active_scanners: string[] }>('/config/scanners', {
    method: 'GET',
  })
}

export async function setGlobalScanner(scanner_names: string[]) {
  return request<{ message: string; active_scanners: string[] }>('/config/scanners', {
    method: 'POST',
    body: JSON.stringify({ active_scanners: scanner_names }),
  })
}

export interface RegexPattern {
  id: number
  name: string
  pattern: string
  entity_type: string
  score: number
  is_active: boolean
}

export async function fetchRegexPatterns() {
  return request<RegexPattern[]>('/regex-patterns/', { method: 'GET' })
}

export async function createRegexPattern(
  name: string,
  pattern: string,
  entity_type: string,
  score: number,
) {
  return request<RegexPattern>('/regex-patterns/', {
    method: 'POST',
    body: JSON.stringify({ name, pattern, entity_type, score }),
  })
}

export async function updateRegexPattern(
  id: number,
  data: { pattern?: string; score?: number; is_active?: boolean },
) {
  return request<RegexPattern>(`/regex-patterns/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function removeRegexPattern(id: number) {
  return request<{ status: string; message: string }>(`/regex-patterns/${id}`, {
    method: 'DELETE',
  })
}
