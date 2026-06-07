# Odysseus HF

```
───────────────────────────────────────────────
 ⊹ ࣪ ˖ ૮( ˶ᵔ ᵕ ᵔ˶ )っ  Odysseus vers. 1.0
───────────────────────────────────────────────
```

![Odysseus](docs/odysseus.jpg)

A self-hosted AI workspace — meant to be the self-hosted version of the UI experience you get from ChatGPT and Claude. But with more jank and fun. Running on your own hardware, with your own data — local-first, privacy-first, and no trojan.

> **This fork** adds [Hugging Face Spaces](https://huggingface.co/spaces) deployment support with **HF Storage Buckets** as persistent cloud storage, so you can run Odysseus in the cloud with zero infrastructure.

## What's New in This Fork

| Feature | Description |
|---------|-------------|
| **HF Spaces Dockerfile** | Self-contained multi-stage `Dockerfile.spaces` — push one file to a Docker Space and it builds everything from GitHub |
| **HF Storage Buckets** | S3-compatible cloud storage powered by [Xet](https://xetdata.com) — persists data across Space restarts |
| **Bucket Management UI** | Create, select, and manage HF buckets directly from **Settings → HF Buckets** |
| **Bucket REST API** | Full CRUD API at `/api/buckets/` for programmatic bucket and file management |
| **Auto-Bucket Bootstrap** | Set `ODYSSEUS_AUTO_BUCKET=1` and a private bucket is created for you on first boot |
| **Entrypoint Bootstrap** | `docker/entrypoint-spaces.sh` handles token validation, bucket setup, ChromaDB startup, and data sync |

## Fork File Map

The following files were added or modified in this fork on top of the [upstream Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) project:

| File | Type | Description |
|------|------|-------------|
| `Dockerfile.spaces` | Added | Multi-stage Docker build for HF Spaces (auto-clones from GitHub) |
| `docker/entrypoint-spaces.sh` | Added | Bootstrap script: token validation, bucket setup, ChromaDB, data sync |
| `src/hf_bucket_storage.py` | Added | `HfBucketStorage` class — Python interface for HF Bucket CRUD and file ops |
| `routes/bucket_routes.py` | Added | FastAPI router at `/api/buckets/` — 12 endpoints for bucket management |
| `static/js/hfBuckets.js` | Added | Front-end UI for bucket creation, selection, file management |
| `.env.example` | Modified | Added HF Bucket environment variables section |
| `README.md` | Modified | Added HF Spaces deployment tutorial and fork documentation |

## Features

| Feature | Description | Technologies |
|---------|-------------|-------------|
| **Chat** | Chat with any local model or API; adding them is super simple | vLLM, llama.cpp, Ollama, OpenRouter, OpenAI, GitHub Copilot |
| **Agent** | Hand it tools and let it run the whole task itself | [opencode](https://github.com/anomalyco/opencode), MCP, web, files, shell, skills, memory |
| **Cookbook** | Scans your hardware, recommends models, click to download and serve | [llmfit](https://github.com/AlexsJones/llmfit), VRAM-aware, GGUF/FP8/AWQ, vLLM/llama.cpp |
| **Deep Research** | Multi-step runs that gather, read, and synthesize sources into a visual report | [Tongyi DeepResearch](https://github.com/Alibaba-NLP/DeepResearch) |
| **Compare** | Compare models side by side — test completely blind, no bias | Multi-model, blind test, synthesis |
| **Documents** | YOU write the text, AI is there to assist, not the opposite | Multi-tab editor, markdown, HTML, CSV, syntax highlighting, AI edits |
| **Memory / Skills** | Persistent memory and skills — your agent evolves over time | ChromaDB, fastembed (ONNX), vector + keyword retrieval, import/export |
| **Email** | IMAP/SMTP inbox with AI triage built in | IMAP, SMTP, per-account routing, CalDAV-aware |
| **Notes & Tasks** | Quick notes with reminders, a todo list, and scheduled tasks | Note pings, checklist, cron-style tasks, ntfy/browser/email channels |
| **Calendar** | Local-first calendar with CalDAV sync | CalDAV pull, .ics import/export, per-calendar colors, agent-aware |
| **HF Buckets** | Cloud storage with HF Storage Buckets — persistent across restarts | huggingface_hub, Xet, S3-compatible, auto-bucket bootstrap |
| **Mobile** | Looks and runs great on your phone, not just desktop | Responsive, installable (PWA), touch gestures |
| **Extras** | More to explore — happy if you give it a go | Image editor, theme editor, file uploads (vision + PDF), web search, presets, sessions, 2FA |

## Demo

A full, hover-to-play tour lives on the landing page (`docs/index.html`).

<details>
<summary>Screenshots / clips</summary>

### Chat & Agents
![Chat & Agents](docs/chat.gif)
### Deep Research
![Deep Research](docs/research.gif)
### Compare
![Compare](docs/compare.gif)
### Documents
![Documents](docs/document.gif)
### Notes & Tasks
![Notes & Tasks](docs/notes.gif)

</details>

## Quick Start

Defaults work out of the box: clone, run, then configure models/search/email inside **Settings**. Only edit `.env` for deployment-level overrides like `APP_BIND`, `APP_PORT`, `AUTH_ENABLED`, `DATABASE_URL`, or a pre-seeded admin password.

On first setup, Odysseus creates an admin account (`admin` unless `ODYSSEUS_ADMIN_USER` is set) and prints a temporary password in the terminal. For Docker installs, the same line is in `docker compose logs odysseus`. Use that for the first login, then change it in **Settings**.

Contributing? See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, testing, and pull request guidelines.

### Deployment Methods at a Glance

| Method | Best For | Port | Auth Default | Persistence | Setup Effort |
|--------|----------|------|-------------|-------------|-------------|
| **Docker Compose** | Local self-hosting | 7000 | Enabled | Local disk | Low |
| **Native Linux/macOS** | Development, Apple Silicon | 7000 / 7860 | Enabled | Local disk | Low |
| **Native Windows** | Windows development | 7000 | Enabled | Local disk | Low |
| **HF Spaces** | Cloud, zero-infrastructure | 7860 | Disabled | HF Buckets | Minimal |

---

### Docker (recommended)

```bash
git clone https://github.com/BF667/odysseus-hf.git
cd odysseus-hf
cp .env.example .env       # optional, but recommended for explicit defaults
docker compose up -d --build
```

To include optional extras in the image (PDF viewer, Office extraction; includes AGPL PyMuPDF), build with `docker compose build --build-arg INSTALL_OPTIONAL=true` before `up`.

Open `http://localhost:7000` when the containers are healthy. Docker Compose binds the web UI to `127.0.0.1` by default. If the port is taken, set `APP_PORT=7001` in `.env` and recreate the container. Set `APP_BIND=0.0.0.0` only when you intentionally want LAN/reverse-proxy access.

### Native Linux / macOS

```bash
git clone https://github.com/BF667/odysseus-hf.git
cd odysseus-hf
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python setup.py
python -m uvicorn app:app --host 127.0.0.1 --port 7000
```

Requirements: Python 3.11+. Cookbook also needs `tmux` for background model downloads and serves. The app itself is lightweight; local model serving is the heavy part and depends on the model, runtime, GPU, and VRAM, so small hosts can connect to API or remote model servers instead. Use `--host 0.0.0.0` only when you intentionally want LAN/reverse-proxy access.

### Apple Silicon

Docker on macOS cannot use the Metal GPU. For GPU-accelerated Cookbook on an M-series Mac, run Odysseus natively:

```bash
git clone https://github.com/BF667/odysseus-hf.git
cd odysseus-hf
./start-macos.sh
```

It launches at `http://127.0.0.1:7860`. To expose it to your phone over a trusted LAN/VPN such as Tailscale, bind all interfaces:

```bash
ODYSSEUS_HOST=0.0.0.0 ./start-macos.sh
# then open http://<tailscale-ip>:7860
```

The script also reads `.env` at startup, so `APP_BIND=0.0.0.0` and `APP_PORT` set there are picked up automatically without a command-line override each run.

Keep `AUTH_ENABLED=true` (the default) before binding outside loopback. Do not expose this port directly to the public internet. To build a clickable app wrapper:

```bash
./build-macos-app.sh
```

<details>
<summary>Cookbook, GPU, Ollama, and troubleshooting notes</summary>

**Docker bundled services.** Compose starts Odysseus, ChromaDB, SearXNG, and ntfy. Odysseus and the bundled service ports bind to `127.0.0.1` by default, so they are reachable from the host but not exposed to your LAN/public internet unless you opt in.

**Cookbook storage in Docker.** Downloads live in `./data/huggingface` (`~/.cache/huggingface` in the container). Cookbook-installed Python CLIs and serve engines live in `./data/local` (`~/.local` in the container), so they survive container recreation.

**Remote servers.** In **Cookbook -> Settings -> Servers**, generate the Odysseus SSH key and add the public key to the remote server's `~/.ssh/authorized_keys`. From the host you can also run:

```bash
ssh-copy-id -i data/ssh/id_ed25519.pub user@server
```

**Docker GPU overlays.** CPU-only users can skip this section. Cookbook can only detect GPUs that Docker exposes to the container — if the host runtime or device passthrough is not configured, Cookbook sees the iGPU, another card, or CPU instead of your intended GPU.

For NVIDIA, `scripts/check-docker-gpu.sh` diagnoses GPU passthrough and can optionally install the host runtime or update `.env`.

```bash
# Read-only diagnostic (default — installs nothing, never edits .env):
scripts/check-docker-gpu.sh

# Print OS-specific install commands without running them:
scripts/check-docker-gpu.sh --print-install-commands

# Install NVIDIA Container Toolkit on Ubuntu/Debian (requires sudo):
scripts/check-docker-gpu.sh --install-nvidia-toolkit

# Write COMPOSE_FILE to .env (only when GPU passthrough is confirmed working):
scripts/check-docker-gpu.sh --enable-nvidia-overlay

# Full assisted setup — install toolkit, then enable overlay if passthrough works:
scripts/check-docker-gpu.sh --install-nvidia-toolkit --enable-nvidia-overlay
```

Safety notes:
- The app never installs host GPU runtime automatically.
- The app never edits `.env` automatically.
- `.env` is only modified when `--enable-nvidia-overlay` is explicitly passed, and only after GPU passthrough succeeds. `--yes` skips prompts but does not bypass the passthrough gate.
- `.env.bak.*` backups created by `--enable-nvidia-overlay` are ignored by Git and the Docker build context.

To enable manually without the script, add this to `.env`:

```bash
COMPOSE_FILE=docker-compose.yml:docker/gpu.nvidia.yml
```

**AMD / ROCm.** AMD setup is read-only diagnostic plus manual `.env` edit. Run:

```bash
scripts/check-docker-amd-gpu.sh
```

Then add the reported values to `.env`, replacing `RENDER_GID` with your host's numeric render group id:

```bash
COMPOSE_FILE=docker-compose.yml:docker/gpu.amd.yml
RENDER_GID=989
```

For NVIDIA/AMD GPU support, also read the comments in the selected overlay file: docker/gpu.nvidia.yml or docker/gpu.amd.yml.

**Stack-management UIs (Portainer, Coolify, Dockhand, etc.).** These tools often accept only a single Compose file and do not reliably honor `COMPOSE_FILE` or multiple `-f` overlays. CLI users should keep using the `COMPOSE_FILE` overlay workflow above. For stack UIs, point the stack at one of the standalone files instead, which bundle the base stack plus the GPU settings:

- `docker-compose.gpu-nvidia.yml` — still requires the NVIDIA Container Toolkit on the host.
- `docker-compose.gpu-amd.yml` — still requires host ROCm/kfd/DRI setup, the `video`/`render` group membership, and `RENDER_GID` when needed.

The base `docker-compose.yml` plus the `docker/gpu.*.yml` overlays remain the source of truth; the standalone files mirror them for single-file deployments.

Verify after enabling either overlay:

```bash
docker compose exec odysseus nvidia-smi -L   # NVIDIA
docker compose exec odysseus sh -lc 'test -e /dev/kfd && test -d /dev/dri && ls -l /dev/kfd /dev/dri/renderD*'  # AMD
```

> **GPU passthrough ≠ llama.cpp CUDA.** `nvidia-smi` passing inside the container confirms Docker GPU access, but llama.cpp also needs `cudart` and the CUDA Toolkit at runtime. If Cookbook logs show `Unable to find cudart library`, `Could NOT find CUDAToolkit`, `CUDA Toolkit not found`, or tensors/layers assigned to CPU, that is a Cookbook/llama.cpp build issue — not a Docker passthrough failure. Re-install the serve engine via **Cookbook → Dependencies** to get a CUDA-enabled build.
>
> The same split applies to AMD/ROCm: seeing `/dev/kfd` and `/dev/dri` inside the container confirms device passthrough, not ROCm userspace or a ROCm-enabled vLLM/llama.cpp build. `rocm-smi` and `rocminfo` are not expected inside the slim Odysseus image.

**Ollama with Docker.** If Ollama runs on the host, add this endpoint in Settings:

```text
http://host.docker.internal:11434/v1
```

Ollama must listen outside its own loopback interface:

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

This connects Odysseus in Docker to an Ollama server that is already running on your host machine; it does not start Ollama inside the container. `host.docker.internal` is Docker's hostname for the host machine from inside the container. Cookbook **Serve** is a separate workflow for serving downloaded models through Odysseus/llama.cpp, so Windows users with an existing Ollama install usually only need to add the endpoint in Settings.

**Useful checks.**

```bash
docker compose ps
docker compose logs --tail=120 odysseus
docker compose logs odysseus | grep -E 'ChromaDB|MemoryVectorStore|DEGRADED'
```

**macOS details.** `start-macos.sh` installs Homebrew deps, creates the venv, runs setup, and starts uvicorn on port `7860` because AirPlay often holds `7000`. It uses llama.cpp/Ollama for Metal. vLLM/SGLang are CUDA/ROCm-only and do not run on macOS. MLX-only models are not served by Odysseus.

</details>

### Native Windows

**One-command launcher** (creates the venv, installs deps, runs setup, starts the server; safe to re-run):

```powershell
git clone https://github.com/BF667/odysseus-hf.git
cd odysseus-hf
powershell -ExecutionPolicy Bypass -File .\launch-windows.ps1
```

Or do it by hand:

```powershell
git clone https://github.com/BF667/odysseus-hf.git
cd odysseus-hf
py -3.11 -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python setup.py
python -m uvicorn app:app --host 127.0.0.1 --port 7000
```

If `python` points at an older interpreter, use `py -3.12` (or another installed 3.11+ version) for the venv step.

**Requirements:** Python 3.11+. The core app (chat, agent, memory, documents, email, calendar, deep research) runs fully native. For full **Cookbook** background model downloads and the agent shell tool, also install [Git for Windows](https://git-scm.com/download/win) (provides `bash.exe`). Local GPU *serving* of vLLM/SGLang needs Linux/WSL2; for a local model on Windows, [Ollama](https://ollama.com/download) is the easiest path — point Odysseus at `http://localhost:11434/v1` in Settings.

Open `http://localhost:7000`, log in with the generated admin password, and configure everything else inside **Settings**.

### Hugging Face Spaces (cloud deployment with HF Bucket storage)

Deploy Odysseus to [Hugging Face Spaces](https://huggingface.co/spaces) as a Docker Space, with **HF Storage Buckets** as your persistent cloud storage. This gives you a free, always-on instance that survives restarts — no server, no reverse proxy, no LAN setup needed.

<details>
<summary>What are HF Storage Buckets?</summary>

HF Storage Buckets are S3-compatible cloud storage provided by Hugging Face, powered by [Xet](https://xetdata.com). They offer a persistent, versioned filesystem that integrates natively with HF Spaces. Each bucket is private by default and scoped to your HF user or organization. You can create and manage buckets through the Odysseus UI or the `huggingface_hub` Python library.

| Property | Details |
|----------|---------|
| **Persistence** | Data survives Space restarts and rebuilds |
| **Privacy** | Buckets are private by default, accessible only with your token |
| **Protocol** | S3-compatible — `hf://buckets/` URI scheme for programmatic access |
| **Regions** | Choose storage region (`us`, `eu`, etc.) when creating a bucket |
| **Cost** | Free tier with generous storage for personal and org use |

Learn more: [HF Buckets documentation](https://huggingface.co/docs/huggingface_hub/en/guides/buckets)

</details>

#### Prerequisites

| Requirement | How to Get It |
|-------------|--------------|
| HF account | Sign up at [huggingface.co/join](https://huggingface.co/join) |
| HF API token (read + write) | Create at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |

That's it — no git, no local clone, no code to push. The Dockerfile clones the repo for you.

#### Step 1 — Create a Docker Space

1. Go to [https://huggingface.co/new-space](https://huggingface.co/new-space)
2. Choose **Docker** as the Space SDK
3. Pick a name (e.g. `odysseus`) and set visibility to **Private** (recommended)
4. Click **Create Space**

#### Step 2 — Configure Space secrets and variables

In your Space's **Settings** page, add the following:

| Type | Name | Value | Required | Description |
|------|------|-------|----------|-------------|
| **Secret** | `HF_TOKEN` | Your HF API token (`hf_xxx...`) | Yes | Needed for Bucket API access and data sync |
| **Variable** | `ODYSSEUS_AUTO_BUCKET` | `1` | Recommended | Auto-creates a private bucket on first boot |
| **Variable** | `ODYSSEUS_HF_BUCKET` | `username/odysseus-data` | Optional | Use a specific existing bucket instead of auto-create |
| **Variable** | `ODYSSEUS_BUCKET_REGION` | `us` | Optional | Storage region for auto-created buckets |

> **Tip:** Set `ODYSSEUS_AUTO_BUCKET=1` for the easiest experience — it creates `username/odysseus-data` automatically and you never need to think about bucket configuration.

#### Step 3 — Push the Dockerfile (that's the only file you need)

The `Dockerfile.spaces` is **self-contained** — it uses a multi-stage build that clones the entire repo from GitHub during the build, so you never need to push the full source code to your Space. Just push the single file:

```bash
# Create an empty repo and push only the Dockerfile
git clone https://huggingface.co/spaces/<your-username>/<your-space-name> my-space
cd my-space

# Download the Dockerfile from this repo
curl -O https://raw.githubusercontent.com/BF667/odysseus-hf/dev/Dockerfile.spaces

# HF Spaces expects the file to be named "Dockerfile"
cp Dockerfile.spaces Dockerfile

git add Dockerfile
git commit -m "deploy odysseus"
git push
```

That's it — one file, one push. HF Spaces detects the `Dockerfile` and starts building. The first build takes 3–5 minutes. Watch the build logs in the Space's **Logs** tab.

**How it works under the hood** — the Dockerfile uses a two-stage build:

```
┌─ Stage 1: Builder ─────────────────────────────────┐
│  python:3.12-slim  +  git + build-essential + cmake │
│                                                     │
│  1. git clone ODSY_REPO (ODSY_BRANCH) → /app       │
│  2. python3 -m venv /opt/venv                       │
│  3. pip install -r requirements.txt                 │
│  4. pip install -r requirements-optional.txt        │
│  5. pip install huggingface_hub[hf_xet] xet        │
│  6. python setup.py                                 │
│                                                     │
│  → produces /opt/venv + /app                        │
└──────────────────────┬──────────────────────────────┘
                       │ COPY --from=builder
                       ▼
┌─ Stage 2: Final ───────────────────────────────────┐
│  python:3.12-slim  +  curl + tmux (no build tools) │
│                                                     │
│  COPY /opt/venv  →  /opt/venv                      │
│  COPY /app       →  /app                           │
│                                                     │
│  EXPOSE 7860                                        │
│  ENTRYPOINT entrypoint-spaces.sh                    │
│  CMD python -m uvicorn app:app --port 7860          │
└─────────────────────────────────────────────────────┘
```

Stage 1 (builder) does all the heavy lifting — cloning, compiling, and installing everything into a virtual environment. Stage 2 (final) copies only the built venv and app files into a clean slim image, dropping git, build-essential, cmake, and other build-only tools. The final image is significantly smaller and has a smaller attack surface.

The repo URL and branch are configurable via build args:

| Build Arg | Default | Description |
|-----------|---------|-------------|
| `ODSY_REPO` | `https://github.com/BF667/odysseus-hf.git` | Git repo URL to clone |
| `ODSY_BRANCH` | `dev` | Branch or tag to checkout |

To deploy a fork or a different branch, edit the `ARG` lines at the top of `Dockerfile.spaces` before pushing. For example, to pin a specific release tag:

```dockerfile
ARG ODSY_BRANCH=v1.2.0
```

Or to clone your own fork:

```dockerfile
ARG ODSY_REPO=https://github.com/yourname/odysseus-hf.git
ARG ODSY_BRANCH=main
```

#### Step 4 — Wait for it to come up

When the build finishes, the entrypoint script (`docker/entrypoint-spaces.sh`) automatically:

| Step | Action | Details |
|------|--------|---------|
| 1 | **Validates HF token** | Logs a warning if `HF_TOKEN` is missing |
| 2 | **Creates or selects a bucket** | `ODYSSEUS_AUTO_BUCKET=1` → creates `username/odysseus-data`; `ODYSSEUS_HF_BUCKET` → uses that bucket directly |
| 3 | **Syncs existing data** | If the bucket has files from a previous run, they are pulled down so you pick up where you left off |
| 4 | **Starts ChromaDB** | Local embedded instance on port 8100 (no separate container needed) |
| 5 | **Launches Odysseus** | On port 7860, bound to `0.0.0.0` so HF's reverse proxy can reach it |

Once healthy, open your Space URL:

```
https://<your-username>-<your-space-name>.hf.space
```

Auth is **disabled by default** on HF Spaces (`AUTH_ENABLED=false`) since HF Spaces already gates access through your Space's visibility setting (Private = only you). If you want an additional login layer, set `AUTH_ENABLED=true` as a Space variable and configure credentials in Settings.

#### Managing buckets from the UI

Once Odysseus is running, go to **Settings → HF Buckets** to:

| Action | Description |
|--------|-------------|
| **View status** | See which bucket is active, your HF user info, and storage usage |
| **Create a new bucket** | Specify a name, privacy level, and region |
| **Select an existing bucket** | Pick from a list of your buckets to use as the active storage target |
| **Upload / download / delete files** | Manage individual files inside the active bucket |
| **Sync local uploads** | Push all local `data/uploads/` files to the bucket for cloud backup |
| **Update your HF token** | Change or refresh the token without redeploying |

#### Bucket REST API

All bucket operations are also available as REST API endpoints under `/api/buckets/`:

| Endpoint | Method | Description | Request Body |
|----------|--------|-------------|-------------|
| `/api/buckets/status` | GET | Current configuration and active bucket | — |
| `/api/buckets/list` | GET | List your buckets | — |
| `/api/buckets/create` | POST | Create a new bucket | `{ name, private?, namespace?, region? }` |
| `/api/buckets/select` | POST | Set active bucket | `{ bucket_id }` |
| `/api/buckets/clear` | POST | Clear active bucket | — |
| `/api/buckets/info/{id}` | GET | Bucket metadata | — |
| `/api/buckets/delete/{id}` | DELETE | Delete a bucket (irreversible) | — |
| `/api/buckets/upload` | POST | Upload a file | Multipart form: `file`, `remote_path?`, `bucket_id?` |
| `/api/buckets/files` | GET | List files in bucket | Query: `prefix?`, `recursive?`, `bucket_id?` |
| `/api/buckets/files/delete` | POST | Delete files from bucket | `{ paths: [...], bucket_id? }` |
| `/api/buckets/sync` | POST | Sync a directory to bucket | `{ local_dir, remote_prefix?, bucket_id? }` |
| `/api/buckets/sync-uploads` | POST | Sync local uploads to bucket | — |
| `/api/buckets/token` | POST | Update HF token | `{ token }` |

#### How persistence works on HF Spaces

HF Spaces are ephemeral — the container filesystem resets on each rebuild. HF Storage Buckets solve this by providing external cloud storage that persists across restarts. Here is the data flow:

```
┌─────────────────────────────────────────────┐
│              HF Space Container             │
│                                             │
│  Odysseus app  ←→  data/uploads/  ←→  HF   │
│       │                │            Bucket   │
│       ▼                ▼              │      │
│   data/app.db    Sync on startup   ┌──┴──┐  │
│   data/chromadb/  ←──────────────→ │cloud│  │
│   settings.json                     │store│  │
│                                     └─────┘  │
└─────────────────────────────────────────────┘
```

| Event | What Happens |
|-------|-------------|
| **On startup** | The entrypoint pulls existing files from the bucket into `data/uploads/` so previously uploaded content is available immediately |
| **During use** | File uploads go to local `data/uploads/` and can be synced to the bucket via the UI or API |
| **On restart** | The cycle repeats — the entrypoint re-syncs from the bucket, so no data is lost |

For database persistence (`data/app.db`, ChromaDB data), you can also sync these to the bucket by calling `POST /api/buckets/sync` with `local_dir` set to `data/`. For automated backup, consider scheduling a sync via the Notes & Tasks cron feature.

#### Troubleshooting HF Spaces

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Dockerfile not found" build error | Wrong filename | Ensure the file is named `Dockerfile` (not `Dockerfile.spaces`) in your Space repo |
| Build fails during `git clone` | HF build runner can't reach GitHub | Check HF Spaces status; as fallback, push the full repo to your Space with the standard `Dockerfile` |
| "No HF_TOKEN set" warning in logs | Missing secret | Add `HF_TOKEN` as a **Secret** (not a Variable) in Space settings |
| Bucket creation fails | Token lacks write permission | Edit your token at [settings/tokens](https://huggingface.co/settings/tokens) and enable Buckets permission |
| "Runtime error" in Space | ChromaDB startup failure | Check logs; ensure port 8100 is not already in use inside the container |
| Data disappeared after rebuild | No bucket configured | Set `ODYSSEUS_AUTO_BUCKET=1` or `ODYSSEUS_HF_BUCKET=username/bucket-name` as a Space variable |
| Want standard Dockerfile instead | Running locally, not HF | Use the standard `Dockerfile` with `docker compose up -d --build` |
| Want to deploy a fork or custom branch | Need different source | Edit the `ARG ODSY_REPO` and `ARG ODSY_BRANCH` lines at the top of `Dockerfile.spaces` |

</details>

## Configuration

Most setup is done inside the app with `/setup` or **Settings**. Use `.env` for deployment-level defaults and secrets you want present before first boot.

### Environment Variables

#### Core Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_BIND` | `127.0.0.1` | Host bind address. Use `0.0.0.0` only for intentional LAN/reverse-proxy access |
| `APP_PORT` | `7000` | Port for the web UI |
| `AUTH_ENABLED` | `true` | Enable/disable login |
| `LOCALHOST_BYPASS` | `false` | Dev-only auth bypass for loopback requests. Keep false for shared deployments |
| `SECURE_COOKIES` | `false` | Set true when serving through HTTPS at a trusted proxy |
| `DATABASE_URL` | `sqlite:///./data/app.db` | Database connection string |
| `ODYSSEUS_ADMIN_PASSWORD` | — | Pre-seed the first admin password during setup |

#### LLM & Models

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_HOST` | `localhost` | Your LLM server (e.g. `llm-host.local:8000`) |
| `LLM_HOSTS` | — | Comma-separated list for model discovery |
| `OPENAI_API_KEY` | — | Optional OpenAI key. Prefer adding providers in the app unless pre-seeding |
| `OLLAMA_BASE_URL` | — | Ollama endpoint (Docker: `http://host.docker.internal:11434/v1`) |
| `LM_STUDIO_URL` | — | LM Studio endpoint (Docker: `http://host.docker.internal:1234`) |
| `RESEARCH_LLM_ENDPOINT` | — | Research service LLM endpoint |
| `LLM_CA_BUNDLE` | — | Extra CA bundle for providers with custom TLS chains |

#### Search & Web

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARXNG_INSTANCE` | `http://localhost:8080` | SearXNG URL. Docker overrides to `http://searxng:8080` |
| `SEARXNG_SECRET` | Generated on first Docker boot | Optional SearXNG cookie/CSRF secret |
| `ALLOWED_ORIGINS` | localhost-only | CORS allowed origins |

#### ChromaDB & Embeddings

| Variable | Default | Description |
|----------|---------|-------------|
| `CHROMADB_HOST` | `localhost` | ChromaDB host. Docker overrides to `chromadb` |
| `CHROMADB_PORT` | `8100` | ChromaDB port. Docker overrides to `8000` |
| `EMBEDDING_URL` | — | OpenAI-compatible embeddings endpoint |
| `EMBEDDING_API_KEY` | — | Embedding API key |
| `EMBEDDING_MODEL` | — | Embedding model name |
| `FASTEMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local fallback embedding model (ONNX) |

#### Hugging Face Buckets

| Variable | Default | Description |
|----------|---------|-------------|
| `HF_TOKEN` | — | HF API token for Bucket access, model downloads, and fastembed |
| `ODYSSEUS_HF_BUCKET` | — | Pre-selected HF bucket ID (e.g. `username/bucket-name`) |
| `ODYSSEUS_AUTO_BUCKET` | — | Set `1` to auto-create a bucket on first boot (HF Spaces) |
| `ODYSSEUS_BUCKET_REGION` | `us` | Storage region for auto-created buckets |
| `ODYSSEUS_HF_SPACES` | `0` | Set `1` when running inside an HF Space (adjusts ports, disables auth) |

#### Misc

| Variable | Default | Description |
|----------|---------|-------------|
| `CLEANUP_INTERVAL_HOURS` | `24` | Cleanup interval in hours |
| `ODYSSEUS_INPROCESS_POLLERS` | `1` | In-process email pollers (set to 0 for external cron) |
| `ODYSSEUS_INPROCESS_TASKS` | `1` | In-process scheduled-task runner (set to 0 for external driver) |
| `ODYSSEUS_SCRIPT_HOST` | `localhost` | Host for built-in "run_script" scheduled-task action |

### Optional Dependencies

`requirements-optional.txt` contains packages that unlock extra features. It is not installed by default.

| Package | Feature Unlocked |
|---------|-----------------|
| `faster-whisper` | Local speech-to-text (microphone → text) via the "local" STT provider |
| `duckduckgo-search` | DuckDuckGo as a search provider option |
| `PyMuPDF` | PDF page rendering in the side viewer panel and form-filling (AGPL-3.0) |
| `markitdown` | Office/EPUB document text extraction (.docx/.xlsx/.pptx/.xls/.epub → Markdown) |

### Built-in MCP servers (optional setup)

Odysseus auto-registers a few built-in MCP servers at startup. The npx-based ones (currently the browser server, `@playwright/mcp`) only start when their npm package is already in the local npx cache. If a package isn't cached, that server is skipped with a startup log message explaining what to do, so a fresh install does not block on a multi-minute npm download or hang if Playwright system deps are missing.

To enable the browser MCP (page navigation, screenshots, vision), run once:

```bash
npx -y @playwright/mcp@latest --version
```

That installs `@playwright/mcp` plus Playwright (~300MB total). Restart Odysseus and the server will register at startup.

## Architecture

```
app.py                   # FastAPI entry point
core/      auth, database, middleware, constants
src/       llm_core, agent_loop, agent_tools, chat_processor, search/
           hf_bucket_storage.py  — HF Bucket cloud storage backend
routes/    chat, session, document, memory, model … endpoints
           bucket_routes.py      — HF Bucket management API
services/  docs, memory, search, hwfit (Cookbook) …
static/    index.html + app.js + style.css + js/ (modular front-end)
           js/hfBuckets.js       — Bucket UI (create, select, manage)
docker/    entrypoint-spaces.sh  — HF Spaces bootstrap script
Dockerfile.spaces               — HF Spaces-optimized Docker image
docs/      landing page (index.html) + preview clips
```

## Data

All user data lives in `data/` (gitignored):

| Path | Contents |
|------|----------|
| `data/app.db` | SQLite database — sessions, messages, documents |
| `data/memory.json` | Memory store |
| `data/presets.json` | Preset configurations |
| `data/uploads/` | User-uploaded files |
| `data/personal_docs/` | Personal documents |
| `data/chroma/` | ChromaDB vector store data |
| `data/settings.json` | Application settings |
| `data/hf_bucket_settings.json` | HF Bucket configuration (fork addition) |

## Internal Ports

| Port | Service |
|------|---------|
| `7000` | Odysseus raw app port (default for Docker Compose) |
| `7860` | Odysseus app port on HF Spaces |
| `8080` | SearXNG |
| `8091` | ntfy |
| `8100` | ChromaDB host port for manual/compose access |
| `11434` | Ollama |
| `8000-8020` | Common local model/provider APIs |

## Troubleshooting & Advanced Setup

### `chromadb-client` conflicts with embedded ChromaDB

If `chromadb-client` (the lightweight HTTP-only package) is installed alongside the full `chromadb` package, Odysseus starts but ChromaDB silently falls back to HTTP-only mode and fails.

**Fix:** uninstall `chromadb-client` and force-reinstall the full package:
```bash
./venv/bin/pip uninstall chromadb-client -y
./venv/bin/pip install --force-reinstall chromadb
```

### HTTPS + LAN/Tailscale exposure

To expose Odysseus on a local network or Tailscale with HTTPS:
1. Change the bind address to `0.0.0.0` in `.env` (`APP_BIND=0.0.0.0` or `ODYSSEUS_HOST=0.0.0.0`).
2. Generate a locally-trusted cert for your LAN/Tailscale IPs using [mkcert](https://github.com/FiloSottile/mkcert):
   ```bash
   mkcert -install
   mkcert -cert-file cert.pem -key-file key.pem 192.168.1.100 tailscale-ip
   ```
3. Run `uvicorn` with the generated certs:
   ```bash
   python -m uvicorn app:app --host 0.0.0.0 --port 7000 --ssl-certfile=cert.pem --ssl-keyfile=key.pem
   ```
4. Install the `mkcert` CA on any other device you want to access Odysseus from (e.g., for iOS, email the `rootCA.pem` to yourself, install the profile, and trust it in Certificate Trust Settings).

## Security Notes

Odysseus is a self-hosted workspace with powerful local tools: shell access, file uploads, model downloads, web research, email/calendar integrations, and API tokens. Treat it like an admin console.

- Keep `AUTH_ENABLED=true` for any network-accessible deployment.
- Keep `LOCALHOST_BYPASS=false` outside local development.
- Use `SECURE_COOKIES=true` when Odysseus is served through HTTPS by a trusted reverse proxy or private access gateway.
- Do not expose it directly to the public internet without HTTPS and a trusted reverse proxy or private access layer.
- Keep `.env`, `data/`, `logs/`, databases, uploads, generated media, backups, auth/session files, API keys, and model/provider tokens out of Git and private shares. They are ignored by default.
- Review `data/auth.json` after first boot: disable open signup unless you intentionally want it, make only your own account admin, and keep demo/test accounts non-admin.
- Non-admin users do not get shell/Python/file read/write by default, and admin-only routes/tools such as MCP management, API tokens, webhooks, model/cookbook serving, backup/vault, and app settings are admin-gated. Other features are controlled by per-user privileges, so review each user's privileges before exposing a deployment.
- Rotate any API keys or tokens that were ever pasted into a shared chat, demo, screenshot, or log.
- If you enable API tokens or webhooks, create separate tokens per integration and delete unused ones.
- Prefer binding manual development runs to `127.0.0.1`; bind to `0.0.0.0` only when you intentionally want LAN/reverse-proxy access.
- Keep ChromaDB, SearXNG, ntfy, Ollama, vLLM, llama.cpp, databases, and raw model/provider APIs internal-only. Expose only the authenticated Odysseus web/API entrypoint through your trusted proxy or private access layer.
- Before publishing a fork, run `git status --short` and confirm no private files from `.env`, `data/`, `logs/`, uploads, backups, or local databases are staged.

### Private or proxied deployments

Odysseus serves plain HTTP on its app port. Docker Compose binds Odysseus and the bundled services to `127.0.0.1` by default, so a typical production/private setup is:

1. Keep Odysseus on localhost, for example `127.0.0.1:7000`.
2. Terminate HTTPS at a trusted reverse proxy or private access gateway.
3. Put the authenticated Odysseus web/API entrypoint behind that layer.
4. Keep raw service and model ports internal-only.

Cloudflare Access, Tailscale, Caddy, nginx, and Traefik can all fit this pattern; none are required by Odysseus. If your access layer reaches Odysseus on the same host, proxy to `http://127.0.0.1:7000` and keep `AUTH_ENABLED=true`, `LOCALHOST_BYPASS=false`, and `SECURE_COOKIES=true`.

## Contributing

Help is welcome. The best entry points are fresh-install testing, provider setup bugs, mobile/editor polish, docs, and small focused refactors. See [ROADMAP.md](ROADMAP.md) for the current help-wanted list.

## Star History

<a href="https://www.star-history.com/?repos=pewdiepie-archdaemon%2Fodysseus&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=pewdiepie-archdaemon/odysseus&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=pewdiepie-archdaemon/odysseus&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=pewdiepie-archdaemon/odysseus&type=date&legend=top-left" />
 </picture>
</a>

## License

MIT — see [LICENSE](LICENSE) and [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md).

```
                                  |
                                 |||
                                |||||
                  |    |    |   |||||||
                 )_)  )_)  )_)   ~|~
                )___))___))___)\  |
               )____)____)_____)\\|
             _____|____|____|_____\\\__
             \                       /
       ~^~^~~^~^~~^~^~~^~^~~^~^~~^~^~~^~^~~^~^~
               ~^~  all aboard!  ~^~
       ~^~^~~^~^~~^~^~~^~^~~^~^~~^~^~~^~^~~^~^~
```
