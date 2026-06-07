#!/usr/bin/env bash
# docker/entrypoint-spaces.sh — Bootstrap script for Hugging Face Spaces
#
# This script runs before the main app and:
# 1. Auto-configures HF token from Space secrets
# 2. Optionally creates/selects an HF Storage Bucket
# 3. Syncs data from the bucket if available
# 4. Starts a local ChromaDB instance
# 5. Reports on configured/missing secrets
#
# Environment variables (set as HF Spaces secrets/variables):
#   HF_TOKEN            — Required. Your Hugging Face API token.
#   ODYSSEUS_HF_BUCKET  — Optional. Bucket ID to use (e.g. "username/odysseus-data").
#                         If not set and ODYSSEUS_AUTO_BUCKET=1, creates one automatically.
#   ODYSSEUS_AUTO_BUCKET — Set to "1" to auto-create a bucket if none is configured.
#   ODYSSEUS_BUCKET_REGION — Optional. Region for auto-created bucket (default: "us").
#   GITHUB_CLIENT_ID    — Optional. GitHub OAuth App client ID.
#   GITHUB_CLIENT_SECRET — Optional. GitHub OAuth App client secret.
#   OAUTH_REDIRECT_BASE_URL — Optional. Public URL for OAuth callbacks.
#
# All secrets/variables should be set via the HF Spaces Settings UI:
#   https://huggingface.co/docs/hub/spaces-overview#managing-secrets
#   .env files are NOT persistent in HF Spaces — use Space secrets instead.

set -e

echo "=== Odysseus HF Spaces Bootstrap ==="

# ── 1. HF Token ────────────────────────────────────────────────────────────
if [ -z "$HF_TOKEN" ] && [ -z "$HUGGING_FACE_HUB_TOKEN" ]; then
    echo "WARNING: No HF_TOKEN set. HF Bucket and Space secret features will be disabled."
    echo "Set HF_TOKEN as a Space secret to enable cloud storage."
    echo "See: https://huggingface.co/docs/hub/spaces-overview#managing-secrets"
fi

# Ensure at least one token env var is set for the app
export HF_TOKEN="${HF_TOKEN:-$HUGGING_FACE_HUB_TOKEN}"
export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"

# ── 2. Secrets Status Report ──────────────────────────────────────────────
echo ""
echo "── Secrets Status ──────────────────────────────────────"
check_secret() {
    local key="$1"
    local label="$2"
    local required="${3:-optional}"
    if [ -n "${!key}" ]; then
        echo "  ✓ $key ($label) — set"
    else
        if [ "$required" = "required" ]; then
            echo "  ✗ $key ($label) — MISSING (required)"
        else
            echo "  ○ $key ($label) — not set ($required)"
        fi
    fi
}

check_secret HF_TOKEN "HF API Token" "required"
check_secret GITHUB_CLIENT_ID "GitHub OAuth Client ID" "recommended"
check_secret GITHUB_CLIENT_SECRET "GitHub OAuth Client Secret" "recommended"
check_secret OAUTH_REDIRECT_BASE_URL "OAuth Redirect URL" "optional"
check_secret ODYSSEUS_HF_BUCKET "HF Bucket ID" "optional"
check_secret ODYSSEUS_AUTO_BUCKET "Auto-Create Bucket" "optional"
check_secret OPENAI_API_KEY "OpenAI API Key" "optional"
check_secret LLM_HOST "LLM Host" "optional"
check_secret SEARXNG_INSTANCE "SearXNG URL" "optional"
check_secret CHROMADB_HOST "ChromaDB Host" "optional"
check_secret CHROMADB_PORT "ChromaDB Port" "optional"
check_secret EMBEDDING_URL "Embedding URL" "optional"
check_secret EMBEDDING_API_KEY "Embedding API Key" "optional"
check_secret EMBEDDING_MODEL "Embedding Model" "optional"

echo ""
echo "Tip: Set secrets via the HF Spaces Settings UI:"
echo "     https://huggingface.co/spaces/${SPACE_ID:-YOUR_SPACE}/settings"
echo "─────────────────────────────────────────────────────────"
echo ""

# ── 3. Auto-create/select bucket ───────────────────────────────────────────
if [ -n "$HF_TOKEN" ] && [ -n "$ODYSSEUS_AUTO_BUCKET" ]; then
    # Wait for the app to be importable
    echo "Auto-configuring HF Storage Bucket..."
    python3 -c "
import os, json

token = os.getenv('HF_TOKEN')
bucket_id = os.getenv('ODYSSEUS_HF_BUCKET')
region = os.getenv('ODYSSEUS_BUCKET_REGION', 'us')

settings_path = 'data/hf_bucket_settings.json'
os.makedirs('data', exist_ok=True)

# If bucket ID is provided, just set it as active
if bucket_id:
    settings = {'active_bucket_id': bucket_id}
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)
    print(f'Active bucket set to: {bucket_id}')
else:
    # Try to auto-create a bucket
    try:
        from huggingface_hub import HfApi, create_bucket
        api = HfApi(token=token)
        user_info = api.whoami()
        username = user_info.get('name', 'unknown')
        bucket_name = 'odysseus-data'

        try:
            result = create_bucket(
                f'{username}/{bucket_name}',
                private=True,
                exist_ok=True,
                region=region,
                token=token,
            )
            bucket_id = result.bucket_id
            print(f'Bucket ready: {bucket_id}')
        except Exception as e:
            print(f'Bucket creation: {e}')
            bucket_id = f'{username}/{bucket_name}'

        settings = {'active_bucket_id': bucket_id}
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=2)
        print(f'Active bucket set to: {bucket_id}')
    except ImportError:
        print('huggingface_hub not available — skipping bucket setup')
    except Exception as e:
        print(f'Auto-bucket setup failed (non-fatal): {e}')
" || echo "Bucket setup skipped (non-fatal)"
fi

# ── 4. Pull data from bucket (if configured) ───────────────────────────────
if [ -n "$HF_TOKEN" ] && [ -f "data/hf_bucket_settings.json" ]; then
    BUCKET_ID=$(python3 -c "import json; print(json.load(open('data/hf_bucket_settings.json')).get('active_bucket_id',''))" 2>/dev/null || echo "")
    if [ -n "$BUCKET_ID" ] && [ "$BUCKET_ID" != "None" ]; then
        echo "Pulling data from bucket: $BUCKET_ID"
        # Use hf buckets sync to pull data down (if any exists)
        hf buckets sync "hf://buckets/$BUCKET_ID/uploads" "data/uploads" 2>/dev/null || echo "No remote uploads to sync (this is normal for new buckets)"
    fi
fi

# ── 5. Start ChromaDB locally (embedded) ───────────────────────────────────
echo "Starting local ChromaDB..."
pip install chromadb 2>/dev/null || true
chroma run --host 127.0.0.1 --port 8100 --path data/chromadb &
CHROMADB_PID=$!
echo "ChromaDB started (PID: $CHROMADB_PID)"

# Wait for ChromaDB to be ready
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:8100/api/v1/heartbeat > /dev/null 2>&1; then
        echo "ChromaDB is ready"
        break
    fi
    echo "Waiting for ChromaDB... ($i/30)"
    sleep 1
done

# ── 6. Run the main app ────────────────────────────────────────────────────
echo "Starting Odysseus..."
exec "$@"

# Cleanup on exit
trap "kill $CHROMADB_PID 2>/dev/null" EXIT
