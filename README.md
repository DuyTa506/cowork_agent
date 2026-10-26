# AI Document Processing System (0.2.0)

The system runs on a local network (LAN): a document repository with per-unit access control, hybrid search (keyword + semantic) on Qdrant, format checking against Circular 68 on document formatting (the `doccheck` tool), and an AI assistant (Q&A, summarization, drafting) running on models configured by the administrator. This is a **development build**, not a system approved for processing classified or otherwise sensitive information.

The user interface is in Vietnamese; menu and screen names below are translated.

## 1. Feature status

**Available (backend, with tests):**

- Login, password change, account management; roles `admin`, `commander`, `reviewer`, `staff`.
- **Document repository**: multi-file upload (DOC/DOCX/PDF), per-unit deduplication, background processing (read → extract metadata → determine unit and classification → index) with statuses `uploaded → processing → ready | needs_review | needs_ocr | failed`; view content, download the original file, edit extracted metadata by hand, reprocess, delete.
- **Per-unit access control**: users can read documents of their own organizational unit and its subordinate units (org chart in `backend/app/org/units.yaml`); classified documents are readable only by the `commander` role. Filtering happens inside the SQL/Qdrant query, not afterwards.
- **Admin → System** (API): configure the chat model, embedding, rerank, OCR, format checking, upload limits; API keys are encrypted in the database and never returned; servers outside the internal network must be explicitly confirmed; per-item connection test; reindexing when the embedding changes.
- Audit log (login, upload, view, download, edit, delete, settings changes).
- **Format check** (separate screen, nothing is stored in the repository): checks against Circular 68 and spelling with `doccheck`; pick individual fixes, apply them as Track Changes or directly; download the fixed copy, the annotated copy and the report; optionally save to the repository.
- **Spell check** (separate screen `/chinh-ta`, nothing is stored in the repository): paste text or pick a Word file, a PDF with a text layer, `.txt` or `.md`; suspected misspellings get a wavy underline in place and are listed by error type with suggestions and confidence; choose what to fix, ignore correct words (proper names, terms), fix Word files as Track Changes or directly, edit the text right on the screen, download the fixed copy and the report. Same temporary-file mechanism as Format check (API: `docs/SPELLCHECK_API.md`).
- **AI assistant** (DeepSeek Harness): Q&A over the repository strictly within the asker's permissions, with citations that open the source document; whole-document summaries (single pass, or section by section for long documents); quick attachments used only within the conversation; shows what the assistant did (reasoning, searches run in parallel); stop mid-answer.
- **Drafting canvas**: 17 document types (official letters, plans, reports, decisions...) based on Circular 68 templates; the system fills in the national header and the document header from the author's unit (a department issues under the name of its parent body; the reference code and the "Lưu" (file copy) line follow the drafting department, user-editable); the assistant only fills in blanks and *proposes* edits to text the user wrote; format-checks the rendered draft, exports DOCX, saves to the repository.
- **Per-unit writing style**: the assistant follows the general rules of Circular 68 (`backend/app/drafting/style_rules.yaml`, reviewed by domain experts) and a style profile per unit × document type learned from the repository (structure, common opening/closing sentences, legal bases, recipients, signer, terminology); units with few documents inherit the structure from their parent unit; plus sample documents of the same type close to the topic, within the user's permissions. On the canvas, users also pick a style (Unit standard, Report to leadership, Directive to subordinates) and a level of detail (Short, Medium, Full). Proposed paragraph edits are checked deterministically: no invented figures, proper names or dates, and no words the rules forbid. Classified documents are never used (see 8.2).
- Agent tools (MCP, per conversation): `search_documents`, `list_documents`, `read_document`, `search_attachments`, `read_attachment`, `summarize_document`, `canvas_*` (including `canvas_style`: looks up the writing style of the user's unit).
- React UI (light/dark, fully offline): login, Repository, Format check, Spell check, AI assistant + Canvas, Admin; Ctrl+K for quick search.

**Not yet available:** exporting statistics reports to a file (the Statistics page `/thong-ke` exists, see `GET /api/stats`). **OCR** (Peppercorn v3 through an OpenAI-compatible endpoint run by the serving repo) is wired up and has run on 208 scans of the sample corpus; the checkpoint is the d48sh build without RL, so it may repeat or cut off on hard pages. The assistant has been tried with a real LLM (Qwen3.6-35B) in the dev environment; it must be tested with the production model and real data before use.

## 2. Architecture

```text
Browser on the LAN
  │  http://SERVER-IP:8080
  ▼
Nginx (frontend + reverse proxy)
  │ /api/*
  ▼
api  (FastAPI) ───── PostgreSQL   (users, documents, job queue, settings, audit)
  │
worker (same image: python -m app.worker) ── read file → doccheck → chunk → embedding → Qdrant
  │
  ├─ MinIO (S3)        (original files of documents and attachments; the bucket is created on first run)
  ├─ per-conversation agent (DeepSeek Harness + MCP tool process, spawned by api)
  ├─ Qdrant            (hybrid index: dense vectors + BM25; permission filter inside the query; separate collection for attachments)
  └─ Model server      (LLM, embedding, rerank, OCR – OpenAI-compatible; address set by the administrator)

Original files (documents, attachments): MinIO object store (S3), volume minio_data; temporary data: volume app_data (/data/tmp)
```

Backend source code (`backend/app`):

| Package | Role |
|---|---|
| `core` | environment config, database, security (password hashing, JWT), errors, logging, schema upgrades |
| `models` | database tables (User, Document, Job, AppSetting, AuditLog, ChatSession/Message/Attachment, Draft, CheckSession) |
| `schemas` | API request/response shapes |
| `services` | business logic: accounts, documents, job queue, processing pipeline, indexing, settings (`services/settings`), audit |
| `api` | thin FastAPI routers that only call `services` |
| `worker` | job queue processing loop |
| `parsing`, `search`, `org` | reading administrative documents; indexing + search; units and permissions |
| `rag` | the agent's MCP tools (search, read, summarize, canvas) and the asker's identity (signed token) |
| `agent` | DeepSeek Harness profile, per-conversation agent process lifecycle, turning events into displayed steps and citations |
| `drafting` | document templates (taken from doccheck's Circular 68 requirements table), draft content and per-part ownership, DOCX builder |

In the default configuration only web port `8080` is exposed to the LAN; PostgreSQL and the API only talk inside the Docker network. Internal API docs are at `/api/docs`.

## 3. Recommended development tools (as of Oct 14, 2026)

- **Visual Studio Code**, current stable release.
- **Node.js 24 LTS** to run Vite/React; Node.js 24 is the LTS line listed on the official site.
- **Python 3.14.x** (use the latest 3.14.x patch release if all libraries and server infrastructure are approved). The Dockerfile uses `python:3.14-slim`.
- **Docker Desktop + WSL 2** for testing on Windows 11 Pro/Enterprise; on Windows Server, check container platform support and your organization's policy — according to Docker's documentation, Docker Desktop is not officially supported on Windows Server.
- PostgreSQL runs as a container in the deployment configuration.

Official links:
- Node.js: https://nodejs.org/en/download/
- Python: https://www.python.org/downloads/
- React: https://react.dev/versions
- Vite: https://vite.dev/guide/ and https://vite.dev/releases
- FastAPI + Docker: https://fastapi.tiangolo.com/deployment/docker/
- Docker Desktop/WSL 2: https://docs.docker.com/desktop/setup/install/windows-install/
- Local Ollama API (optional): https://github.com/ollama/ollama/blob/main/docs/api/introduction.mdx

## 4. Recommended VS Code extensions

Open **Extensions** (`Ctrl+Shift+X`) and search for/install:

1. `Python` — `ms-python.python`
2. `Pylance` — `ms-python.vscode-pylance`
3. `ESLint` — `dbaeumer.vscode-eslint`
4. `Prettier - Code formatter` — `esbenp.prettier-vscode`
5. `Container Tools` — `ms-azuretools.vscode-containers`
6. `WSL` — `ms-vscode-remote.remote-wsl` (if developing on WSL)
7. `EditorConfig for VS Code` — `EditorConfig.EditorConfig`
8. `REST Client` — `humao.rest-client` (send test API requests from `.http` files)

The recommended list is also in `.vscode/extensions.json`.

## 5. Option A — Development directly in VS Code (no Docker)

This is convenient for editing code. The backend uses SQLite in development, the frontend runs on Vite.

### 5.1 Setup

1. Install VS Code, Node.js 24 LTS and Python 3.14.x (or a Python version verified as compatible under your organization's IT standards).
2. Extract the source and open the project folder in VS Code.
3. Open the integrated terminal (`Terminal > New Terminal`).
4. Run the backend in one terminal:

```powershell
cd backend
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install --find-links wheels -r requirements-dev.txt   # doccheck is installed from the wheels/ folder
$env:DATA_DIR = "./data"                                   # defaults to SQLite inside DATA_DIR
$env:QDRANT_URL = "http://127.0.0.1:6333"                  # needs a running Qdrant (docker compose up -d qdrant)
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open a separate terminal for the worker (processes uploaded files), with the same environment variables:

```powershell
python -m app.worker
```

No embedding server yet: log in as admin → **System → Embedding**, pick the `hash` type (for testing the pipeline only, no semantics; disabled when `APP_ENV=production`).

Run the tests: `python -m pytest tests` from the `backend` folder (needs a running Qdrant; the assistant tests start a real agent against the fake model `tests/fakellm.py` and take a few tens of seconds).

If PowerShell does not allow activating the virtual environment, skip the `Activate.ps1` line and call `.\.venv\Scripts\python.exe` directly.

5. Open a second terminal for the frontend:

```powershell
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

6. Open on the dev machine: `http://localhost:5173`.
7. Development API docs: `http://localhost:8000/api/docs`.
8. The first account is seeded by the backend: username `admin`, password from the `ADMIN_PASSWORD` environment variable; if it is not set, the demo value `ChangeMe123!` is used. Change the password right after logging in.

**Access from other machines in development mode:** port `5173` must be opened in the firewall, and the backend proxy calls loopback `127.0.0.1:8000` on the dev machine, so the current dev setup works best on the dev machine itself. For many concurrent users, use Option B below.

## 6. Option B — LAN deployment with Docker Compose (recommended for multi-user demos)

### 6.1 Prepare the server

1. Prefer a Linux server managed by your organization, or Windows 11 Pro/Enterprise with Docker Desktop + WSL 2 for a pilot.
2. Install Docker Engine/Docker Compose (Linux) or Docker Desktop (Windows 11). Confirm that `docker compose version` works.
3. Extract the source into a fixed folder, for example `C:\Apps\ai-document` or `/opt/ai-document`.
4. Copy `.env.example` to `.env` and **set your own strong passwords** for the database/admin/MinIO (`MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` have no defaults; without them `docker compose` will not start) and a long random `JWT_SECRET`. Do not share the `.env` file with unauthorized people.
5. Run PowerShell in the root folder:

```powershell
.\scripts\start-server.ps1
```

Or run the commands manually:

```powershell
Copy-Item .env.example .env   # first time only, then edit .env
notepad .env
docker compose up --build -d
docker compose ps
docker compose logs -f api worker web
```

6. Get the server's IPv4 address:

```powershell
ipconfig
```

7. On the server: `http://localhost:8080`; from other machines on the same LAN: `http://<SERVER-IP>:8080`.
8. If other machines cannot connect: check that they are on an allowed network/VLAN, that the firewall opens TCP `8080` only to approved machines/groups, and that no other service is using the port.
9. Health check: `http://<SERVER-IP>:8080/api/health`. API docs: `http://<SERVER-IP>:8080/api/docs`.

### 6.2 Is the address stable?

The access address is `http://SERVER-IP:8080`. For an address that never changes, ask your network administrator for a **static IP/DHCP reservation** for the server, and optionally an internal DNS name, for example `http://ai-docs:8080`. Do not use example IP addresses before checking the real IP on your network.

### 6.3 Admin commands

```powershell
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f web
docker compose restart api
docker compose down            # stop containers, keep the data volumes
docker compose down -v         # DELETES the data volumes — do not run unless you mean it
```

## 7. Air-gapped (offline) deployment

If the target server has no Internet access:

1. On an intermediate machine that is allowed to reach registries/packages, review the source code and `.env`, then run `scripts/export-offline.ps1` to build the images and package them into a single TAR file.
2. Transfer the source code, the image TAR and the reviewed `.env` file through a transfer method your organization permits. The `.env` file contains credentials and must be protected separately.
3. On the target server, install Docker Engine, put the source in a fixed folder, place the `.env` file according to policy, and put the TAR next to `docker-compose.yml`.
4. Run `scripts/import-offline.ps1` to load the images and start without building or downloading packages.
5. Note: verify checksums, image provenance and dependencies, and run security scans according to your organization's rules before bringing anything onto the production network.

### 7.1 Object store (original files)

The original files of documents and attachments are stored in **MinIO** (S3-compatible), no longer on the API volume. Configure it with environment variables (infrastructure, not changeable at run time): `OBJECT_STORE=s3|local`, `S3_ENDPOINT` (`host:port`), `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_SECURE`. MinIO is not needed for development: `OBJECT_STORE=local` (the default) writes to `DATA_DIR/objects`. Original-file downloads support `Range` (page-by-page PDF viewing) and are streamed, never holding the whole file in memory. The MinIO console only listens on `127.0.0.1:9001` on the server.

Image note: `minio/minio` can no longer be pulled from Docker Hub (checked on Oct 26, 2026: `pull access denied`); the pinned `RELEASE.2025-09-07T16-13-09Z` is available on the dev machine and `scripts/export-offline.ps1` packs it into the TAR (together with api, web, postgres and qdrant; the bundle tested on Linux is ~835 MB). Keep this TAR; to switch to another S3 server, just change `S3_*` and the service in docker-compose (the code uses the standard S3 protocol).

Upgrading from the version that stored files on a volume: run `docker compose exec api python -m app.storage.migrate --delete` once (copies every file into MinIO; safe to rerun). Backup: back up the `minio_data` volume together with PostgreSQL and Qdrant.

### 8.0 Input moderation and deep spell check

- **Moderation**: keyword rules (`app/moderation/lexicon.yaml`) + a ViSoBERT classifier fine-tuned on ViHSD (CLEAN/OFFENSIVE/HATE) running on ONNX Runtime on CPU. The model files are not in git: run `python tools/export_moderation_model.py` once (needs Internet, torch + transformers), then copy `backend/models/visobert-hsd/` to the offline machine; without the files only the rules run. Measured on 30 hand-written offensive / 20 normal sentences: the rules catch 19/30, rules + model 29/30, 1/20 false positive (the phrase “chó nghiệp vụ”, "service dog", is already excluded); on 4,000 real passages from the repository: 0 passages flagged by the model at threshold 0.9. The default threshold is 0.95.
- **Deep spell check**: doccheck's GECToR model needs the ONNX Runtime library; the application uses the library shipped in the `onnxruntime` package (the same 1.31 version doccheck pins). Turn it off or pick the model in Admin → System → Format check. doccheck's GECToR weights carry a research (non-commercial) license: see doccheck's `THIRD_PARTY_LICENSES.txt` before using it beyond internal research.

## 8. Model configuration (LLM, embedding, rerank, OCR)

No model is hard-coded. The `admin` account goes to **Admin → System** to enter the server address, model name and API key, then clicks *Test connection* before saving. The environment variables in `.env.example` (LLM, `EMBEDDING_*`, `RERANK_*`, `OCR_*`) are only defaults for the first run.

- Servers must be OpenAI-compatible (`/v1/chat/completions`, `/v1/embeddings`); rerank uses `/rerank` with the `cohere` protocol (vLLM, Jina) or `tei`. The intramind serving layer uses the `intramind` type for both: embedding at `/api/v1/embed` (applies the query prefix itself, you only enter the dimension) and rerank at `/api/v1/rerank` (no model name needed).
- **OCR** (optional): enable it in Admin → OCR with the address and model name of the serving server. Scanned PDFs are rendered page by page (longest side up to 2048 px) and each image is sent to the model on its own with the `grounding` prompt (reads block by block: headings, paragraphs, tables; can be turned off with the *Read by block* checkbox; the first lines of a document are not merged into one paragraph); the recognized text is saved as an `.ocr.docx` file next to the original for viewing, search and citation; downloads still return the original PDF. Reprocessing does not run OCR again. Chat attachments also use OCR. With OCR off, scanned PDFs stay in the "Needs OCR" state.
- **Quick-fill the serving connection**: `python backend/tools/apply_serving.py --host <serving host>` sets the LLM, embedding (`intramind`), rerank and OCR to match the serving repo (ports 8201, 8204, 8205; change them with `--llm-port`, `--adapter-port`, `--ocr-port`), then you click *Test connection* in Admin. Addresses outside the internal network still have to be confirmed in the UI.
- **Recommended configuration** (from offline measurements with `backend/tools/eval_rerank.py`, 200 auto-generated questions on the sample corpus): Harrier embedding through the `intramind` type (640 dimensions); enable Rerank with bge-reranker-v2-m3 (`cohere` or `tei` protocol) or the intramind serving layer's rerank (`intramind` type, slightly worse), *Passages sent to rerank* = 30. Rerank raises doc@1 from 0.675 to 0.84; with rerank on, the differences between embedding models are negligible. These numbers come from sample data and must be measured again on the real repository. Changing the embedding requires reindexing the whole repository.
- **Rerank** (optional): when enabled, the assistant's search tool takes the first *Passages sent to rerank* passages from hybrid search, lets the model reorder them and keeps the best `top_k`. If the rerank server fails, search still works in the original order.
- Addresses **outside the internal network** will receive document content, so the system requires the administrator to confirm such a server before saving; the confirmation is recorded in the audit log.
- API keys are encrypted in the database with the `SETTINGS_KEY` key (or a key derived from `JWT_SECRET`); the UI only shows "set/not set".
- **Changing the embedding model or dimension** makes the old vectors unusable: the system switches to a new Qdrant collection (its name contains the configuration fingerprint) and the administrator clicks *Reindex*. While it runs, search results are incomplete; do it outside working hours.
- Do not point to public AI service URLs for processing internal data.

### 8.0.1 Viewing documents as original pages

The browser renders pages with pdf.js (the library, CMap fonts and worker ship with the frontend bundle; nothing is fetched from the Internet). Word files are converted to PDF on the server with **LibreOffice** (`soffice`, preinstalled in the backend image; when running directly, install `libreoffice-writer` and `fonts-liberation`), once while the document is processed, and saved next to the original. The page view uses the fonts installed on the server: Liberation is metric-compatible with Times New Roman/Arial so lines break in the right places; other fonts (VnTime, Arial Narrow...) are substituted. For an existing repository, backfill with `cd backend && python tools/build_previews.py --workers 4`.

### 8.1 Importing a whole folder of documents

```bash
cd backend
python tools/import_corpus.py "/path/to/corpus"     # add --limit 20 to try it out; rerunnable, files already imported are skipped
python -m app.worker                                 # run several processes to go faster (use PostgreSQL for a real repository)
```

Each .doc/.docx/.pdf file becomes a document owned by the administrator; the unit comes from the folder path (for example `Department/Division/...`), files under a folder named `văn bản mật` ("classified documents") are marked as classified, and folders that are not recognized map to the root unit. The `phan_loai_pdf` folder (sorted copies) is skipped. Broken, empty or password-protected files are logged as errors without stopping the batch. The system tags documents automatically (year, topic, scan) during processing; users browse the repository by unit, type, year and tag in the left panel of the Repository page.

### 8.2 Per-unit style profiles

After importing (and whenever many documents are added), rebuild the style profiles the drafting assistant uses:

```bash
cd backend
python tools/build_style_profiles.py        # writes DATA_DIR/style/profiles.json; ~3,500 documents: ~45 seconds, ~0.5 GB RAM
```

The tool reads the passages indexed in Qdrant, skips classified documents, and for each unit (including its subordinate units) × document type extracts: the issuing body, reference code and "Lưu" line from *recent* documents (a renamed body uses its new name); the structure of major/minor sections; common opening and closing sentences (numbers and dates masked); legal bases, recipients and the signer's title; the unit's characteristic terms. An item enters a profile only when it appears in at least 3 documents; in profiles that merge several units (higher-level bodies) it must appear in at least 2 units, so that one office's own content does not become a shared "convention". When drafting, a unit with fewer than 5 documents of the same type takes its structure and sample sentences from the nearest parent unit; legal bases, recipients and signer come only from the unit itself. Without profiles, the document header follows the org chart and the assistant follows only the general rules. The general rules (Circular 68, the repository's consistent word usage, three styles, three levels of detail and phrases to avoid) are in `backend/app/drafting/style_rules.yaml` and can be edited without programming. When writing a section, the assistant calls `canvas_style(section=...)` to get the first sentence or two of that section in sample documents; sample sentences are only for learning the writing style. Each proposed paragraph edit is compared with the original paragraph (figures, dates, reference numbers, unit names, person names) and with the list of words to avoid; warnings appear right under the proposal and are returned to the assistant. Sections that at least 60% of the unit's documents of the same type contain but the draft lacks are listed in the check tab, as suggestions only. Accepting, rejecting or revising the assistant's paragraphs is recorded so that the Statistics page can count acceptance and revision rates; the content itself is not shown on that page.

## 9. Known limitations

- The format rules come from `doccheck` (Circular 68); have a records-management expert validate them before treating them as official.
- With OCR off, scanned PDFs and PDFs with broken fonts stop at `needs_ocr`; PDFs that have a text layer the reader cannot read are also retried with OCR.
- The assistant runs one agent process per open conversation (at most 16 at once; processes idle for 15 minutes are stopped); the first answer takes about 10 seconds to start if the agent has not been started beforehand. The number of agent steps is not limited yet (to be set after testing with the real model).
- The agent uses the pre-release `deepseek-harness-sdk 0.2.1rc2` (pinned to the exact version, in `backend/wheels`).
- The assistant's answer currently arrives all at once after the steps (the harness reports per step, not per token).
- Semantic search quality depends on the chosen embedding model; offline evaluation shows BM25 is strong on administrative documents, so both the `keyword` and `hybrid` modes are kept.
- Classified documents are visible only to the `commander` role, even to the uploader if they have a regular role; users without a valid unit cannot upload.
- Penetration testing, a permission review, backup/restore, hardening, HTTPS and load testing are needed before production use.

## 10. First-run steps

1. Log in with the admin account set in `.env`; change the password.
2. Go to **Admin → System**: configure the embedding (required for indexing) and the LLM; click *Test connection* for each.
3. Create an account for each user and assign the correct **unit** (it determines which documents they see); do not share accounts.
4. Upload a few sample documents **that you are allowed to use**; watch the processing status and check which fields need completing.
5. Review the logs in Admin.

## 11. Directory structure

```text
.
├── backend/
│   ├── app/              # core, models, schemas, services, api, worker, parsing, search, org, rag, agent
│   ├── tests/            # python -m unittest discover -s tests -p "test_*.py"
│   ├── tools/            # offline tools: corpus surveys, sample-corpus indexing, retrieval evaluation
│   └── wheels/           # doccheck and DeepSeek Harness (installed at build time, no Internet needed)
├── frontend/src/         # React UI (see frontend/docs/ARCHITECTURE.md)
├── design-system/        # design system: MASTER.md (tokens, layout), COMPONENTS.md (component set)
├── docs/                 # documentation
├── scripts/              # start, stop, offline build, offline import
├── docker-compose.yml    # db, qdrant, api, worker, web
├── .env.example
└── README.md
```
