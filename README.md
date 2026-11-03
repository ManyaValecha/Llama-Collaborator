# Llama-Collaborator — An Adaptive AI Engineering Partner

A local engineering workspace where specialist agents route and critique work, use durable project memory, adapt explanations, analyze user-selected images, research current documentation, prepare code changes, and report verification evidence. The implementation is original; LORE, UpRabbit, and Wand inform the product ideas, not the source code or assets.

## Start locally

Requires Python 3.10+.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add a key for the configured OpenAI-compatible provider as MODEL_API_KEY=...
uvicorn main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). API reference: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). The app defaults to offline mode until a key is configured. Offline guidance varies by request type and is labeled as local triage; it does not claim model inference, live research, or code execution. If the configured provider fails, the app makes one bounded attempt and completes the rest of the turn with local guidance instead of stalling on repeated role calls. SQLite data is stored in `backend/data/`.

The app supports OpenAI-compatible Responses APIs. The supplied local configuration uses [OpenRouter](https://openrouter.ai/docs) with Meta Llama 4 Maverick and OpenRouter's web search server tool. The provided credential is an OpenRouter key, so this runs a Meta model through OpenRouter; it is not a Meta-hosted Model API credential. If judging requires Meta-hosted API usage specifically, replace it with an eligible Meta API key and endpoint. You can switch providers by editing `MODEL_API_BASE`, `MODEL_NAME`, and `MODEL_API_KEY` in `backend/.env`. Requests may incur usage charges on your provider account. OpenRouter documents its [Responses API](https://openrouter.ai/docs/api/api-reference/responses/create-responses), [Meta Llama models](https://openrouter.ai/meta-llama), and [web search tool](https://openrouter.ai/tool/web-search/).

## Implemented workflow

1. Enter an engineering request, use voice input when your browser supports it, or attach a screenshot/source file.
2. The router classifies the request and assigns distinct architect, debugger, coder, researcher, verifier, coach, and vision roles as appropriate.
3. Specialists use recent conversation, matching active project decisions, and the saved comfort profile. Only research and security-review routes call the provider's search tool; cited links appear when the provider returns them.
4. The chat can load source files from the configured workspace. To draft a patch, the app shows which files will be sent to the configured model provider. It previews the exact diff, then requires a second approval before applying changes. The apply token is single-use and expires after five minutes; stale files are rejected.
5. The verification action is separately approved. If Docker is available, Python source is parsed in a network-disabled, read-only container. Otherwise, the app offers a clearly labeled local AST parse that does not import or execute code. Neither mode claims that unit or integration tests ran.
6. Conversations, structured project decisions, and the comfort setting persist locally in SQLite. Decision records support provenance, affected paths, rationale, rejected alternatives, confidence, lifecycle status, dependencies, security relevance, and a review date. The live graph reflects saved decisions and dependency links; health checks flag invalid references, dependency cycles, active memories that rely on superseded decisions, and overdue review dates. Older free-form memories are retained during the schema migration.
7. The guided demo seeds a labeled token-security decision and attaches an intentionally flawed Python fixture. It exercises the same route, memory retrieval, specialist flow, and approval UI as a normal request. Selecting it sends that sample request and source file to the configured provider and may incur usage charges.

### Privacy and action boundaries

- Prompts and attached content are sent to the configured model provider when you submit a model request. Patch drafting displays the selected workspace paths and asks you to confirm before sending their contents. Voice input uses the browser’s speech-recognition service, which may process audio externally; recognized text is sent to the model provider only when you submit it.
- Responses requests use `store: false`; provider-side request handling and retention policies still apply.
- Source files are read from `LLAMA_WORKSPACE_ROOT` (defaults to this project directory); hidden paths, secrets, dependency folders, symlinks, and unsupported file types are excluded from workspace selection and edits.
- A proposed patch never writes files by itself. The user reviews the complete diff and approves applying those exact edits.
- The built-in verifier only parses Python syntax; it does not run project code, unit tests, or integration tests. With Docker it uses a network-disabled, read-only container. Without Docker the approved fallback parses source on the host without importing or executing it. No arbitrary shell command is exposed.
- Browser research uses the configured model provider's search tool. This MVP does not perform pointer-based control of arbitrary browser pages or stream a live desktop screen.

## Configuration

Edit `backend/.env`:

```env
MODEL_API_BASE=https://openrouter.ai/api/v1
MODEL_API_KEY=your_key_here
MODEL_NAME=meta-llama/llama-4-maverick
MODEL_API_TIMEOUT_SECONDS=90
MODEL_REASONING_EFFORT=medium
LLAMA_MEMORY_DB=./data/llama-collaborator.sqlite3
# Optional: a local source tree. Relative paths are resolved from the backend process directory.
LLAMA_WORKSPACE_ROOT=../path-to-your-project
```

Keep `.env` out of version control. Restart the backend after changing environment variables.

## API surface

- `GET /api/health` — provider, model, workspace, and sandbox availability.
- `POST /api/turn` — route task, retrieve memory, and run role-specific model calls.
- `GET /api/conversations` and `GET /api/conversations/{id}` — local conversation history.
- `GET /api/workspace/files` and `GET /api/workspace/file?path=...` — restricted source file selection.
- `POST /api/changes/propose` and `POST /api/changes/apply` — generate a diff and apply only after one-time approval.
- `POST /api/verification/preview` and `POST /api/verification/run` — preview and run isolated syntax verification.
- `POST /api/memory`, `GET /api/memory/{project_id}`, `GET /api/memory/{project_id}/health` — structured project decisions and validation.
- `GET/POST /api/profile/comfort` and `POST /api/feedback` — restore and adjust the saved explanation preference.
- `POST /api/demo/prepare` — prepare the bundled, clearly labeled guided debugging scenario.

## Local checks

From the repository root, install the development HTTP test dependency and run the core checks with:

```bash
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v
```

## Current scope

This is a local hackathon MVP, not a hosted production service. It does not include hosted deployment, user accounts, PostgreSQL/pgvector, collaborative multi-user permissions, a full browser-control runtime, or a general arbitrary-code test runner. A configured key enables model inference, but a live provider request has not been included in local checks because it can incur usage charges. Docker enables isolated parsing; without Docker, the explicit local parse fallback is used.

## Reviewer materials

- [Architecture, data flow, and action boundaries](docs/architecture.md)
- [Three-minute judge demo script](docs/demo-script.md)
- [Devpost submission draft](docs/submission-draft.md)
- **Run guided demo** in the workspace for the reproducible token-claims scenario.
- GitHub Actions runs the core backend checks and validates the browser script syntax on pushes and pull requests.

## Inspiration

- [LORE — Living Organizational Record Engine](https://devpost.com/software/lore-living-organizational-record-engine?utm_source=chatgpt.com) and the friend’s [LORE GitLab project](https://gitlab.com/gitlab-community/community-projects/2026-02-ai-hackathon/35153311) informed the lifecycle memory and decision validation ideas. This implementation uses its own schema, code, and UI.
- [UpRabbit — Collaborative Knowledge Building with Agents](https://devpost.com/software/thought-visualized?utm_source=chatgpt.com)
- [Wand — A live agent that sees, browses, and clicks with you](https://devpost.com/software/wand-a-live-agent-that-sees-browses-and-clicks-with-you)
