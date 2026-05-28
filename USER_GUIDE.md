# 🤖 Corporate Onboarding Assistant V2 — User & Administrator Guide

Welcome to the **Corporate Onboarding Assistant V2** guide. This document provides step-by-step instructions for setting up, running, interacting with, and maintaining the assistant. 

---

## 📋 Table of Contents
1. [Introduction & Key Features](#1-introduction--key-features)
2. [Prerequisites & System Setup](#2-prerequisites--system-setup)
3. [Running the Application](#3-running-the-application)
4. [User Guide: Navigating the Chat Interface](#4-user-guide-navigating-the-chat-interface)
5. [Role-Based Access & Test Accounts](#5-role-based-access--test-accounts)
6. [Security Guardrails & Session Cost Management](#6-security-guardrails--session-cost-management)
7. [Admin CLI Operations & Maintenance](#7-admin-cli-operations--maintenance)
8. [Ingesting New Onboarding Documents](#8-ingesting-new-onboarding-documents)

---

## 1. Introduction & Key Features

The **Corporate Onboarding Assistant V2** is a stateful, multi-turn AI chatbot designed to guide new hires through IT setups, leave policies, health insurance schemes, and payroll configurations. Under the hood, it uses **LangGraph** to coordinate routing, **ChromaDB** for semantic document retrieval, and **Redis** for two-tier high-performance caching.

### 🌟 Key Features
* **Stateful Conversations**: Remembers history (last 10 turns, with older turns summarized) so users can ask natural follow-up questions.
* **Smart Checklist Progress**: Automatically updates a customizable checklist of onboarding tasks (e.g., IT setup, insurance, payroll) as users ask questions and verify tasks.
* **Hybrid Two-Tier Caching**: Uses L1 (Redis exact match) and L2 (ChromaDB semantic similarity) to deliver sub-5ms cached responses and slash API token costs.
* **Input/Output Safety Guardrails**: Hardened protection against Prompt Injections, Toxicity, PII leakage, and API Key exposure.
* **Resilient Fallback RAG**: Automatically falls back to local flat-file parsing (`onboarding_faq.txt`) if databases or embedding APIs fail, displaying a degraded status warning in the UI.

---

## 2. Prerequisites & System Setup

Ensure you have the following installed on your machine:
* **Python 3.10+** (Recommend a virtual environment)
* **Docker Desktop** (to run Redis cache container)
* **Git** (to manage workspace versioning)

### Step 1: Environment File Configuration
Create a `.env` file in the root directory of the application:

```env
# Gemini API credentials
GOOGLE_API_KEY=YOUR_GEMINI_API_KEY

# Redis configuration URL
REDIS_URL=redis://localhost:6379/0

# Optional LangSmith Tracing configurations
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=YOUR_LANGCHAIN_API_KEY
LANGCHAIN_PROJECT=corporate-onboarding-assistant-v2

# Cost control budget limit per session in USD (e.g. 50 cents)
SESSION_BUDGET_USD=0.50
```

### Step 2: Establish Virtual Environment & Dependencies
Open your command prompt/terminal (PowerShell or Bash) in the application directory:

```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (CMD):
.venv\Scripts\activate.bat
# Linux/macOS:
source .venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
```

### Step 3: Spin Up Local Services
Start the local Redis server container (used for L1 Caching and Session Rate Limiting):

```powershell
docker run -d --name local-redis -p 6379:6379 redis:7.2-alpine
```

---

## 3. Running the Application

### Step 1: Ingest Initial Onboarding Knowledge Base
Before starting the chatbot, parse the onboarding files inside the `data/` directory and populate your vector store:

```powershell
python rag/ingest.py
```
> [!NOTE]
> The ingestion script reads files (PDF, Word, Markdown, Text) from the `data/` directory, extracts their contents, chunks them, generates vector embeddings, and stores them in `chroma_db/`.

### Step 2: Launch Streamlit Web UI
To launch the user interface, run:

```powershell
streamlit run app.py
```
Your default browser will open automatically. If it does not, copy and paste the URL from the terminal output (default: `http://localhost:8501`).

---

## 4. User Guide: Navigating the Chat Interface

```
┌─────────────────────────────────────────────────────────────┐
│ 👤 Onboarding Assistant UI                     [Log Out]    │
├───────────────┬─────────────────────────────────────────────┤
│               │                                             │
│  User Profile │  🤖 Corporate Onboarding Assistant         │
│  Role: Joinee │  ─────────────────────────────────────────  │
│               │  User: How do I request a laptop?           │
│  Task List    │  Bot: According to IT Setup Policy [1]...    │
│  [x] IT Setup │                                             │
│  [ ] Payroll  │  Sources:                                   │
│  [ ] Benefits │  [1] data/IT_Setup_Guide.pdf                │
│               │                                             │
├───────────────┴─────────────────────────────────────────────┤
│  [ Type your onboarding question here...               ] 📤 │
└─────────────────────────────────────────────────────────────┘
```

### 🔐 1. Logging In
When the app launches, you will see a clean login prompt. Enter your credentials (see [Section 5](#5-role-based-access--test-accounts) below for test logins).

### ⚙️ 2. The Interactive Sidebar
The sidebar acts as your onboarding dashboard:
* **Active User Role**: Displays your current authenticated role.
* **Onboarding Checklist**: Displays your custom checklist items. Tasks are dynamically marked as checked (e.g., `[x] IT Setup Completed`) as your conversations progress.
* **Session Usage**: Shows your session API token cost (e.g., `$0.0014`) and warns you when approaching the `$0.50` guardrail budget.

### 💬 3. Chatting & RAG Citations
* Type questions directly into the input bar. 
* Responses will feature interactive source footnotes (e.g., `[data/IT_Setup.pdf]`).
* If a request falls back to the local offline file due to service issues, a `[degraded]` badge or alert warning will alert you to the situation.

### 👍 4. Feedback Loops
* Every response has a 👍 / 👎 button. 
* Giving a 👎 rating saves the prompt into a feedback collection so administrators can investigate and correct inaccurate responses.

---

## 5. Role-Based Access & Test Accounts

The application implements role-gated retrieval (documents with higher permission attributes are blocked from lower-privileged users). Use these pre-configured login profiles for testing:

| Username | Default Password | Assigned Role | Access Scope |
| :--- | :--- | :--- | :--- |
| **`joinee`** | `joinee123` | **Joinee** | General onboarding, leave plans, IT setup instructions. |
| **`hrteam`** | `hr123` | **HR** | Full HR policies, administrative procedures, general onboarding. |
| **`admin`** | `admin123` | **Admin** | Unrestricted access to all documents, systems, and controls. |

> [!WARNING]
> Change the default passwords in `auth_config.yaml` using bcrypt hashes before deploying the application to production.

---

## 6. Security Guardrails & Session Cost Management

The assistant has active guardrails to protect corporate assets and control costs:
* **Rate Limits**: Users are limited to a fixed count of requests per window to prevent spam.
* **PII & Key Scrubbing**: Input questions are sanitized to prevent PII leaks. Response outputs are audited; if any configuration secrets, API tokens, or keys are accidentally retrieved, they are immediately redacted.
* **Override Protections**: Unicode NFKC normalization prevents bypass vectors. Prompt override phrases are automatically blocked.
* **Usage Caps**: If your session billing reaches or exceeds `$0.50`, the system triggers an escalation flow, blocking further calls to conserve API credits.

---

## 7. Admin CLI Operations & Maintenance

Administrators can run the following commands to check application health, run quality assurance tests, or wipe data for compliance:

### 🔍 Static Code Compliance Audit
Audit codebase files to verify strict implementation constraints (such as isolated prompts, pure python execution blocks, and try-catch safety):
```powershell
python agents/auditor.py
```
*Outputs a verification log to `audit_report.json`.*

### 🧪 Run RAG Evaluations & Unit Tests
To evaluate response faithfulness, answer relevancy, guardrails routing, cache division, and rate limits:
```powershell
pytest tests/
```
*Runs all 20+ unit and integration tests under the `tests/` directory.*

### 🧼 GDPR Compliance: Right to Be Forgotten
To wipe all state databases, SQLite checkpoint histories, and conversation memory logs for a specific session ID:
```powershell
python utils/purge_user.py <session_id>
```

### 🧹 Database Housekeeping & Pruning
Wipe SQLite history checkpoints and user logs older than 30 days:
```powershell
python utils/prune_db.py
```

---

## 8. Ingesting New Onboarding Documents

To update or expand the assistant's knowledge base:
1. Place the new document (supporting `.pdf`, `.docx`, `.md`, or `.txt`) into the `data/` directory.
2. Run the ingestion command:
   ```powershell
   python rag/ingest.py
   ```
3. The ingestion tool automatically splits document text recursively, tags required roles (if metadata is set up), generates vector embeddings via the Gemini Embeddings API, and updates the local Chroma database.
4. Restart your Streamlit web server or clear its cache to fetch the latest documents.

---
*For development or support, please check the [codebase_context.md](file:///d:/SR/Main%20Projects/Corporate%20Onboarding%20Assistant%20V2/codebase_context.md) file.*
