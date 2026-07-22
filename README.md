# Database + document chatbot

Agentic workflow architecture exported from **[Agentic LaunchPad](https://github.com)** by Affine Analytics.

> This repository is a scaffold generated from an interactive architecture interview and visual workflow builder. Implement each agent step per the plan below.

## At a glance

- **Session:** `session-1784653133023-k6es1w`
- **Steps:** 7
- **Connections:** 7
- **Exported:** 2026-07-22 12:05 UTC

## Problem statement

Internal analysts and managers need a fast, read-only chatbot that can answer questions across both documents and structured database data without relying on outside knowledge.

## Requirements

### Key requirements

- **Use case:** Provide natural-language answers in a few seconds by combining approved internal document content and tabular data into one response, while flagging conflicts and indicating confidence.
- **Human-in-the-loop:** No human review is required in the normal flow because the system is read-only Q&A for internal users.
- **Data flow:** Analysts and managers submit a natural-language question through the chatbot interface. The system infers likely intent when the question is broad, then retrieves relevant passages from indexed PDF/DOCX documents and relevant rows or aggregates from the internal database in parallel. Retrieved results are compared for conflicts, combined into a single grounded context, and passed to the answer generation layer. The model produces a read-only natural-language answer using only approved internal sources, includes a confidence note when evidence is weak, and flags disagreements by showing both sides rather than choosing one silently. The final answer is returned to the user with no write-back to source systems.
- **Core components:** User question intake, Intent inference for broad questions, Parallel retrieval from document index and database, Conflict detection across sources, Answer synthesis from approved internal sources only, Confidence scoring and response delivery
- **Architectural flow:** User question intake → Intent inference for broad questions → Parallel retrieval from document index and database → Conflict detection across sources → Answer synthesis from approved internal sources only → Confidence scoring and response delivery

### Interview summary

Provide natural-language answers in a few seconds by combining approved internal document content and tabular data into one response, while flagging conflicts and indicating confidence.

### Architecture blueprint

## Provide natural-language answers in a few seconds by combining approved internal document content and tabular data into one response, while flagging conflicts and indicating confidence.

Internal analysts and managers need a fast, read-only chatbot that can answer questions across both documents and structured database data without relying on outside knowledge.

### Integrations

### HITL
No human review is required in the normal flow because the system is read-only Q&A for internal users.

## Architecture summary

This Phase 3 plan implements a fast, read-only internal chatbot that answers from approved documents and structured database data only, with no external knowledge use. The flow starts with a custom intake gateway, then uses the catalog-first orchestration model to infer intent and fan out into parallel document retrieval and SQL execution paths. Retrieved evidence is merged in a custom conflict-and-strength gate, then passed through catalog answer-consolidation agents to produce the final user response.

The architecture is strongly reuse-oriented: 5 of 7 nodes are reuse/adapt decisions, meeting the catalog-first target. Reused Affine agents are Pipeline Intent Classifier for routing, Eryl Semantic RAG Agent Chain for document retrieval, Quin SQL Agent Chain for structured data access, Final Answer Consolidation Agent for grounded synthesis, and Final Answer Rewriter for final response shaping. Custom build is limited to the chatbot intake gateway and the cross-source evidence conflict check, where the catalog does not provide an explicit capability-aligned fit.

The main flow is left-to-right with one entry and one exit: intake -> intent routing -> parallel document and SQL retrieval -> evidence conflict/strength check -> grounded answer synthesis -> confidence-aware response delivery. There is no human-in-the-loop gate because the spec explicitly states that no human review is required in the normal flow. Integrations implied by the spec are the internal document index and the internal database, both accessed read-only.

Primary risks are ensuring the SQL path remains strictly read-only, preventing the answer layer from introducing unsupported world knowledge, and implementing robust conflict detection when document and table evidence disagree or are both weak. The custom evidence gate should standardize evidence payloads from both retrieval systems so the downstream consolidation and rewriting agents can consistently surface both sides and indicate confidence.

## Workflow overview

This architecture has **7** step(s) and **7** connection(s).

### Execution flow

- **Question Intake Gateway** → *user question* → **Intent Inference and Route Selection**
- **Intent Inference and Route Selection** → *document retrieval route* → **Document Retrieval**
- **Intent Inference and Route Selection** → *sql retrieval route* → **Structured Data Query**
- **Document Retrieval** → *document evidence* → **Evidence Conflict and Strength Check**
- **Structured Data Query** → *table evidence* → **Evidence Conflict and Strength Check**
- **Evidence Conflict and Strength Check** → *grounded evidence bundle* → **Grounded Answer Synthesis**
- **Grounded Answer Synthesis** → *draft answer with evidence status* → **Confidence-Aware Response Delivery**

## Agents & steps

### Question Intake Gateway

*agent* · catalog `pipeline_intent_classifier` · **reuse** · Pipeline Intent Classifier

Receives the user’s question and starts the workflow under read-only internal Q&A guardrails.

*Rationale:* Auto-applied: catalog alternative identified during validation.

**Purpose:** Accept the analyst’s natural-language question and admit only read-only internal Q&A requests into the workflow.

**Role:** This is the entry point for every chatbot request. It receives the user question, frames it for orchestration, and passes it into the intent step so the rest of the pipeline can stay focused on retrieval and answer generation.

**Execution:** Receives the user’s question and starts the workflow under read-only internal Q&A guardrails.

**Consumes from:**
- user question from chatbot interface

**Feeds into:**
- Intent Inference and Route Selection

### Intent Inference and Route Selection

*agent* · catalog `pipeline_intent_classifier` · **reuse** · Pipeline Intent Classifier

Infers the likely meaning of the question and routes it into parallel document and SQL retrieval.

*Rationale:* This catalog agent directly matches the routing capability and is suitable for inferring broad intent and selecting downstream paths.

**Purpose:** Infer likely intent for broad questions and route the request into the document and structured-data retrieval paths.

**Role:** After intake, this step interprets what the user is really asking, especially when the prompt is broad or underspecified. It then sends the same request into parallel retrieval branches so document evidence and database evidence can be gathered quickly in the same run.

**Execution:** Infers the likely meaning of the question and routes it into parallel document and SQL retrieval.

**Consumes from:**
- Question Intake Gateway
- user question

**Feeds into:**
- Document Retrieval
- Structured Data Query

### Document Retrieval

*agent* · catalog `eryl_semantic_rag_agent_chain` · **reuse** · Eryl Semantic RAG Agent Chain

Finds relevant evidence from approved internal documents for the current question.

*Rationale:* This agent already supports semantic retrieval over indexed internal documents and fits the document evidence path.

**Purpose:** Retrieve relevant passages from approved indexed internal documents that may help answer the question.

**Role:** This branch handles the unstructured side of the answer. It searches internal PDFs, DOCX files, and other approved document content for semantically relevant passages and forwards that evidence for cross-source comparison.

**Execution:** Finds relevant evidence from approved internal documents for the current question.

**Consumes from:**
- Intent Inference and Route Selection
- document retrieval route

**Feeds into:**
- Evidence Conflict and Strength Check
- document evidence

### Structured Data Query

*agent* · catalog `quin_sql_agent_chain` · **reuse** · Quin SQL Agent Chain

Runs read-only SQL to gather the structured evidence needed to answer the question.

*Rationale:* This agent is a direct fit for read-only SQL generation and execution against internal structured data sources.

**Purpose:** Generate and run read-only SQL to fetch relevant rows, facts, or aggregates from internal structured data.

**Role:** This branch handles the structured-data side of the answer in parallel with document retrieval. It translates the user’s question into safe read-only SQL, executes it against internal tables, and returns the resulting evidence for downstream comparison and synthesis.

**Execution:** Runs read-only SQL to gather the structured evidence needed to answer the question.

**Consumes from:**
- Intent Inference and Route Selection
- sql retrieval route

**Feeds into:**
- Evidence Conflict and Strength Check
- table evidence

### Evidence Conflict and Strength Check

*custom* · **build**

Reconciles document and SQL evidence, flags conflicts, and marks evidence strength before answer generation.

*Rationale:* No catalog match explicitly covers cross-source conflict detection plus weak-evidence gating, so a custom comparison layer is required.

**Purpose:** Compare document and database evidence, detect disagreements, and assess whether support is strong, weak, or incomplete.

**Role:** This is the reconciliation checkpoint after both retrieval branches finish. It merges the two evidence streams into a grounded bundle, marks conflicts instead of silently resolving them, and annotates weak evidence so the answering layer knows how cautious to be.

**Execution:** Reconciles document and SQL evidence, flags conflicts, and marks evidence strength before answer generation.

**Consumes from:**
- Document Retrieval
- Structured Data Query
- document evidence
- table evidence

**Feeds into:**
- Grounded Answer Synthesis
- grounded evidence bundle

### Grounded Answer Synthesis

*agent* · catalog `final_answer_consolidation_agent` · **reuse** · Final Answer Consolidation Agent

Builds a single grounded draft answer from the reconciled internal evidence.

*Rationale:* This agent is the closest direct fit for combining multiple evidence streams into a single grounded answer.

**Purpose:** Compose one grounded draft answer from the approved document and database evidence without adding outside knowledge.

**Role:** Once the evidence has been reconciled, this step turns the evidence bundle into a coherent draft response. It combines both source types into a single natural-language answer while preserving conflict and evidence-strength signals for the final delivery layer.

**Execution:** Builds a single grounded draft answer from the reconciled internal evidence.

**Consumes from:**
- Evidence Conflict and Strength Check
- grounded evidence bundle

**Feeds into:**
- Confidence-Aware Response Delivery
- draft answer with evidence status

### Confidence-Aware Response Delivery

*agent* · catalog `final_answer_rewriter` · **adapt** · Final Answer Rewriter

Polishes the grounded draft into the final user response with confidence and conflict wording preserved.

*Rationale:* This agent can be adapted to preserve conflict flags and append confidence wording while rewriting the final response for users.

**Purpose:** Convert the grounded draft into concise user-facing text that clearly communicates confidence and any source conflicts.

**Role:** This is the final presentation step before the answer is returned to the user. It rewrites the synthesized draft for clarity and speed of consumption while preserving the factual content, conflict flags, and confidence wording determined upstream.

**Execution:** Polishes the grounded draft into the final user response with confidence and conflict wording preserved.

**Consumes from:**
- Grounded Answer Synthesis
- draft answer with evidence status

**Feeds into:**
- final chatbot response to user

## Reuse decisions

- **Question Intake Gateway** — `reuse` → Pipeline Intent Classifier
  - Auto-applied: catalog alternative identified during validation.
- **Intent Inference and Route Selection** — `reuse` → Pipeline Intent Classifier
  - This catalog agent directly matches the routing capability and is suitable for inferring broad intent and selecting downstream paths.
- **Document Retrieval** — `reuse` → Eryl Semantic RAG Agent Chain
  - This agent already supports semantic retrieval over indexed internal documents and fits the document evidence path.
- **Structured Data Query** — `reuse` → Quin SQL Agent Chain
  - This agent is a direct fit for read-only SQL generation and execution against internal structured data sources.
- **Evidence Conflict and Strength Check** — `build` → custom
  - No catalog match explicitly covers cross-source conflict detection plus weak-evidence gating, so a custom comparison layer is required.
- **Grounded Answer Synthesis** — `reuse` → Final Answer Consolidation Agent
  - This agent is the closest direct fit for combining multiple evidence streams into a single grounded answer.
- **Confidence-Aware Response Delivery** — `adapt` → Final Answer Rewriter
  - This agent can be adapted to preserve conflict flags and append confidence wording while rewriting the final response for users.

## Catalog matches

- **Final Answer Consolidation Agent** (`final_answer_consolidation_agent`) — score 0.90
  - Matched for: Provide natural-language answers in a few seconds by combining approved internal
  - Consolidates count and generic row-level analyses into a single natural-language answer based on task_type routing.
- **Eryl Semantic RAG Agent Chain** (`eryl_semantic_rag_agent_chain`) — score 0.90
  - Matched for: User question intake, Intent inference for broad questions, Parallel retrieval f
  - Retrieves and answers from indexed retail policy and unstructured documents (Chocolate_Confectionery_Retail_Policy.docx, emails, guidelines) using Azure AI Search vector + semantic retrieval.
- **GraphRAG Index & Query Agent** (`graphrag_index_query_agent`) — score 0.86
  - Matched for: capability_slot:document_retrieval
  - Indexes per-project KYC documents into a knowledge graph with entity/community extraction and embeddings; answers analyst questions via local, global, drift, or basic search methods.
- **Pipeline Intent Classifier** (`pipeline_intent_classifier`) — score 0.85
  - Matched for: capability_slot:intent_routing
  - Classifies each user question into vision_only, vision_then_unified, or unified_only and flags multi-shelf comparisons for SQL-only routing.
- **Quin SQL Agent Chain** (`quin_sql_agent_chain`) — score 0.85
  - Matched for: capability_slot:structured_sql
  - AutoGen multi-agent chain that generates, executes, and critiques SQL Server queries on mars schema tables (Mars_Sales_Data, shelf_visit, retail_planogram_stocks, etc.) and returns structured sales/inventory insights.
- **Final Answer Rewriter** (`final_answer_rewriter`) — score 0.85
  - Matched for: capability_slot:answer_synthesis
  - Post-processes combined vision+SQL+semantic draft answers into concise structured user-facing text without adding new facts.
- **Planogram Vision LLM Suite** (`planogram_vision_llm_suite`) — score 0.55
  - Matched for: Internal analysts and managers need a fast, read-only chatbot that can answer qu
  - Azure OpenAI vision functions for shelf-level product extraction, row counting, generic row description, daily KPI JSON, and final natural-language shelf answers after Roboflow cropping.

## Open questions

- What database platform and schema should the SQL agent target in production?
- Is an existing internal document index already available, or must indexing be added as a separate upstream process outside this runtime flow?
- Should the final response expose source snippets or table references internally even though formal citations are not required?
- Inferred required_capability=sql_generation for 'Evidence Conflict and Strength Check' because the step strongly matched a known capability class.

## Validation notes

Overall status: **warn**

- [warn] Catalog coverage for 'Document Retrieval' is weak overall (top raw search score 0.0315).
- [warn] Catalog coverage for 'Grounded Answer Synthesis' is weak overall (top raw search score 0.0318).
- [warn] Spec requires human-in-the-loop but no 'human' step appears on the graph.
- [warn] What database platform and schema should the SQL agent target in production?
- [warn] Is an existing internal document index already available, or must indexing be added as a separate upstream process outside this runtime flow?
- [warn] Should the final response expose source snippets or table references internally even though formal citations are not required?
- [warn] Inferred required_capability=sql_generation for 'Evidence Conflict and Strength Check' because the step strongly matched a known capability class.

## Repository contents

| Path | Description |
|------|-------------|
| `README.md` | This overview |
| `workflow.json` | Full architecture graph, reuse decisions, and layout |
| `session.json` | Interview spec and session metadata (when available) |
| `agents/*.json` | Per-step scaffold files for implementation |

## Next steps

1. Review the architecture summary and agent steps above
2. Open `workflow.json` for the complete graph and reuse decisions
3. Implement each step under `agents/` using your runtime of choice
4. Wire integrations and HITL paths described in the requirements

---
*Generated by Agentic LaunchPad on 2026-07-22 12:05 UTC*