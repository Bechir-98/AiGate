Project Context: AI Security & Reversible Anonymization Gateway
1. Executive Summary & Problem Statement
As generative AI adoption scales within the enterprise, employees increasingly input proprietary, customer, and personal data (PII) into public LLM clouds. This risks violating strict data privacy regulations like GDPR (RGPD) and exposing intellectual property to third parties.

This project delivers an AI Security Gateway—a local, lightweight middleware proxy that intercepts all incoming prompts, reversibly anonymizes sensitive data using localized NLP engines, routes the sanitized text to various cloud LLMs, and replaces the placeholder tokens with original data before delivering the final response back to the user. Security advisors use an interactive dashboard to monitor exfiltration attempts, configure custom detection rules, and analyze latency.

2. Technical Ecosystem
Backend API & Orchestration: FastAPI (Python) — Chosen for its native asynchronous capabilities, speed, and standard Pydantic validation.

NLP Detection Core:

Microsoft Presidio: Handles fast, rule-based, and standard deterministic PII detection using regex and pre-trained SpaCy models (specifically supporting English en and French fr pipelines).

GLiNER (v1/v2): Performs zero-shot named entity recognition (NER) for custom, unstructured, or niche corporate entities without needing fine-tuning.

Vault & Caching: Redis — Stores unique placeholder-to-original-text mappings locally with strict Time-To-Live (TTL) expiration policies.

LLM Routing: LiteLLM — Serves as a unified API gateway to handle model routing, rate limiting, cost monitoring, and fallback configurations across multiple model vendors.

Frontend Dashboard: React, TypeScript, Vite — Designed for security analysts to configure policies, audit blocked/exfiltrated entities, and analyze real-time gateway latency metrics.

3. High-Level System Architecture & Lifecycle
[ User Prompt ] ---> [ FastAPI Gateway ] ---> [ NLP Sanitizer ] ---> (Save mappings to Redis)
                                                                             |
[ Sanitized Output ] <--- [ FastAPI Gateway ] <--- [ LiteLLM / Cloud LLM ] <--+ (Sends tokenized prompt)
        |
 (Deanonymize via Redis)
        v
[ Safe Response ]
Phase A: Input Security & Anonymization Dynamic
Request Interception: The gateway receives a raw prompt, chosen security engine policies (e.g., Presidio vs. GLiNER), and specific target languages or labels.

Dynamic Detection: The prompt is analyzed to identify sensitive entities.

Custom Pattern Registration: Security advisors can register custom regex patterns dynamically in the UI. These patterns register directly into Presidio's pipeline at runtime and persist in Redis to handle enterprise-specific ID formats.

Local Vault Vaulting: Detected entities are replaced by unique, request-scoped placeholder tokens containing a session ID (e.g., changing "Alice" to [REQ_123_PERSON_0]).

Caching: The mapping between the token and the original value is saved to Redis with a short lifespan (e.g., 30 minutes) to ensure data never stays stored longer than necessary.

Phase B: Gateway Routing & Processing
Clean Payload Hand-off: The anonymized prompt (free of any real PII) is forwarded to LiteLLM.

Model Execution: LiteLLM dynamically routes the request to the target cloud model, handles API rate limits, tracks consumption costs, and returns the generated answer.

Phase C: Reversible Deanonymization & Output Check
Output Sanitation: The raw response returned from the LLM is scanned for any potential issues (like toxic output, hallucinations, or prompt injection remnants).

Dynamic Replacement (Matching Inverse): The gateway intercepts the response, reads the unique Request ID embedded in the placeholder tokens, queries Redis, and replaces the tokens back with the original sensitive details.

Delivery: The user receives a natural, fully-detailed response as if no security layers were ever present, while the cloud provider only ever saw anonymized metadata.

Phase D: Audit, Policy Control & Observability
Latency Overhead Tracking: The gateway logs the time elapsed during PII detection, database caching, and network round-trips to measure the exact latency induced by the safety layer.

Exfiltration Audits: The frontend dashboard monitors what types of entities (e.g., credit cards, email addresses) users attempt to send out, which models are utilized, and which custom regex rules are triggered most frequently.