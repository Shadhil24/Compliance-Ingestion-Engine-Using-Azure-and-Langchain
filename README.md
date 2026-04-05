# Multimodal Compliance Ingestion Engine

Ingests video from URLs, indexes it with Azure Video Indexer, retrieves policy context from Azure AI Search, and runs RAG-backed compliance checks with Azure OpenAI using a LangGraph workflow.

## Overview

This project is a Python-based multimodal compliance pipeline for auditing video content against regulatory or brand policy rules.

At a high level, the pipeline:

1. Accepts a video URL.
2. Downloads the source media locally.
3. Uploads the asset to Azure Video Indexer.
4. Waits for indexing to complete.
5. Extracts transcript text, OCR text, and metadata.
6. Retrieves relevant compliance rules from Azure AI Search.
7. Sends the transcript, OCR, metadata, and retrieved rules to Azure OpenAI.
8. Returns a structured compliance report.

The current implementation is wired together using LangGraph, with a simple CLI entrypoint in `main.py`.

## Architecture

The workflow is intentionally simple:

`START -> index_video_node -> audio_content_node -> END`

### Node 1: Video Indexing

Implemented in `backend/src/graph/nodes.py` and `backend/src/services/video_indexer.py`.

Responsibilities:

- Validate the input URL.
- Download YouTube video content using `yt-dlp`.
- Authenticate with Azure using `DefaultAzureCredential`.
- Exchange the ARM token for an Azure Video Indexer account token.
- Upload the video to Azure Video Indexer.
- Poll until indexing completes.
- Extract:
  - `transcript`
  - `ocr_text`
  - `video_metadata`

### Node 2: Compliance Audit

Implemented in `backend/src/graph/nodes.py`.

Responsibilities:

- Build an embeddings client for policy retrieval.
- Query Azure AI Search for relevant compliance rules.
- Build a prompt from:
  - transcript
  - on-screen text (OCR)
  - video metadata
  - retrieved rules
- Send the prompt to Azure OpenAI chat.
- Parse the JSON response into:
  - `compliance_results`
  - `final_status`
  - `final_report`

## Project Structure

```text
.
├── backend/
│   ├── data/                     # PDF rulebooks and supporting assets
│   ├── scripts/
│   │   └── index_documents.py    # Loads PDFs and pushes chunks to Azure AI Search
│   └── src/
│       ├── graph/
│       │   ├── nodes.py          # LangGraph nodes
│       │   ├── state.py          # Workflow state schema
│       │   └── workflow.py       # Graph construction
│       └── services/
│           └── video_indexer.py  # Azure Video Indexer integration
├── main.py                       # CLI entrypoint
├── pyproject.toml                # Python dependencies
└── README.md
```

## Core Technologies

- Python 3.10+
- LangGraph
- LangChain
- Azure Video Indexer
- Azure OpenAI
- Azure AI Search
- `yt-dlp`
- `requests`
- `python-dotenv`

## Current Execution Flow

When you run:

```bash
uv run python main.py
```

the app:

- loads environment variables from `.env`
- generates a session-specific `video_id`
- runs the compiled LangGraph app
- prints a compliance report to the terminal

The default entrypoint currently uses a hard-coded sample YouTube URL in `main.py`. If you want to test a different video, update the `video_url` value in `run_cli_simulation()`.

## Prerequisites

Before running the project, you need working Azure resources for:

- Azure Video Indexer
- Azure OpenAI embeddings deployment
- Azure OpenAI chat deployment
- Azure AI Search
- Microsoft Entra app / service principal for authentication to Video Indexer ARM APIs

You also need:

- Python 3.10 or later
- `uv` installed
- outbound network access to Azure services and YouTube

## Environment Variables

This project uses multiple Azure services, and some deployments may live on different Azure OpenAI resources.

### Azure OpenAI for embeddings

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`

### Azure OpenAI for chat

- `AZURE_OPENAI_CHAT_ENDPOINT`
- `AZURE_OPENAI_CHAT_API_KEY`
- `AZURE_OPENAI_CHAT_DEPLOYMENT`

If chat and embeddings live on the same Azure OpenAI resource, the chat-specific endpoint/key can reuse the same values.

### Azure AI Search

- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_API_KEY`
- `AZURE_SEARCH_INDEX_NAME`

### Azure Video Indexer

- `AZURE_VI_NAME`
- `AZURE_VI_LOCATION`
- `AZURE_VI_ACCOUNT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`

### Azure identity / service principal

- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`

### Optional runtime tuning

- `AZURE_VI_MAX_WAIT_SECONDS`
- `AZURE_VI_POLL_INTERVAL_SECONDS`
- `AZURE_VI_TOKEN_REFRESH_SECONDS`

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Create a `.env`

Create a local `.env` file with your Azure credentials and resource configuration.

Do not commit `.env`. It is intentionally ignored by `.gitignore`.

### 3. Index your policy documents

Load your regulatory or internal policy PDFs into Azure AI Search:

```bash
uv run python backend/scripts/index_documents.py
```

This script reads PDFs from `backend/data`, chunks them, embeds them, and uploads them into the configured Azure AI Search index.

### 4. Run the pipeline

```bash
uv run python main.py
```

## Example Output

The CLI prints a summary similar to:

```text
--------Workflow Completed--------

Compliance Audit Report
--------------------------------------------------
Video ID: vid_xxxxxxxx
Video URL: https://www.youtube.com/watch?v=...
Total Compliance Checks: 2
Total Errors: 0
--------------------------------------------------
- [CRITICAL] Claim Validation: Unsubstantiated efficacy claim detected
- [MEDIUM] Required Disclosure: Missing on-screen disclaimer

[FINAL SUMMARY]
The content contains unsupported claims and missing mandatory disclosures.
```

## Retrieval-Augmented Compliance Audit

The compliance stage uses a simple RAG pattern:

1. Embed the transcript + OCR text query.
2. Retrieve the top matching compliance chunks from Azure AI Search.
3. Inject those rules into the LLM system prompt.
4. Ask the LLM to return structured JSON.

This keeps the compliance audit grounded in your indexed rulebooks rather than relying only on model priors.

## Design Notes

- The workflow state is defined in `backend/src/graph/state.py`.
- The video indexing service uses a shared `requests.Session` with retries for more resilient Azure API calls.
- Video Indexer polling is synchronous and currently optimized for simplicity rather than high throughput.
- Chat and embeddings support separate Azure OpenAI resources to handle regional quota differences.

## Known Limitations

- The current entrypoint is CLI-first and uses a hard-coded sample URL.
- The compliance prompt is rule-based but still relies on model output parsing.
- The Video Indexer polling loop is synchronous and can take several minutes depending on Azure processing time.
- The FastAPI server scaffold is not yet implemented for production API usage.
- `backend/scripts/index_documents.py` is intended as the ingestion utility for knowledge-base documents and may need further hardening for large-scale indexing.

## Roadmap Ideas

- Add API endpoints for submitting videos and retrieving audit results.
- Support direct file uploads in addition to YouTube URLs.
- Persist audit runs and results in a database.
- Add background job processing for long-running indexing workflows.
- Improve prompt robustness and schema validation.
- Add tests for graph nodes and service integrations.
- Introduce a `.env.example` for easier onboarding.

## Why This Project Matters

Marketing, brand, and regulated content teams often need to review multimedia assets against fast-changing compliance rules. This project demonstrates how to combine:

- multimodal extraction
- retrieval over policy documents
- LLM-based reasoning
- graph-based orchestration

into a single automated review pipeline.

## License

This repository includes an MIT license.
