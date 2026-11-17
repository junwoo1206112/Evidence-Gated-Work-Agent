# Deterministic Retrieval

## ADDED Requirements

### Requirement: Retrieval MUST be deterministic and offline

The system MUST NOT call network, LLM, embedding, or external vector services during retrieval or gate evaluation. For the same corpus and query, the ranked document IDs MUST be identical across processes.

#### Scenario: Repeated search

- **GIVEN** the checked-in corpus and a fixed query
- **WHEN** retrieval runs twice in separate app instances
- **THEN** the ordered `(document_id, score)` list SHALL be identical

### Requirement: Scoring MUST be absolute

Scores MUST NOT be min-max normalized across the candidate set. The top candidate SHALL not force every other candidate to 1.0.

#### Scenario: Sufficient query

- **GIVEN** the sufficient-evidence demo query
- **WHEN** retrieval returns top-5
- **THEN** the top score SHALL exceed 0.6
- **AND** the runner-up SHALL be below 0.9

### Requirement: Korean particles and bigrams SHALL be handled explicitly

The tokenizer SHALL strip common Korean particles and SHALL include Korean syllable bigrams in BM25. Single-syllable document tokens MUST NOT match long query words by substring.

#### Scenario: Particle-suffixed query

- **GIVEN** the query `계약보증금과 지연배상금을 확인`
- **WHEN** the query is tokenized
- **THEN** the terms SHALL be `계약보증금` and `지연배상금`

### Requirement: Source tiers MUST be separated

Public summaries MUST use `https` URLs on the `law.go.kr` allowlist. Synthetic fixtures MUST use `example.com` and MUST be visibly labeled. Synthetic fixtures MUST NOT satisfy the public citation minimum.

#### Scenario: Synthetic fixture in UI

- **GIVEN** a run whose candidates include a synthetic fixture
- **WHEN** the run page renders
- **THEN** the fixture SHALL carry a `합성 fixture` badge
- **AND** the gate count SHALL exclude it

### Requirement: Retrieval quality claims MUST be bounded

The project SHALL present its retrieval evidence as a small regression ablation, not as general RAG quality.

#### Scenario: Ablation documented

- **GIVEN** `scripts/ablation.py` is executed
- **WHEN** it writes `docs/retrieval-ablation.md`
- **THEN** the document SHALL state the query count, corpus hash, Recall@3, MRR@3, and the non-generalization limit
