#!/usr/bin/env bash
# docker/entrypoint-spaces.sh — Bootstrap script for Hugging Face Spaces
#
# This script runs before the main app and:
# 1. Auto-configures HF token from Space secrets
# 2. Optionally creates/selects an HF Storage Bucket
# 3. Syncs data from the bucket if available
# 4. Starts a local ChromaDB instance
#
# Environment variables (set as HF Spaces secrets/variables):
#   HF_TOKEN          — Required. Your Hugging Face API token.
#   ODYSSEUS_HF_BUCKET — Optional. Bucket ID to use (e.g. "username/odysseus-data").
#                        If not set and ODYSSEUS_AUTO_BUCKET=1, creates one automatically.
#   ODYSSEUS_AUTO_BUCKET — Set to "1" to auto-create a bucket if none is configured.
#   ODYSSEUS_BUCKET_REGION — Optional. Region for auto-created bucket (default: "us").

set -e

echo "=== Odysseus HF Spaces Bootstrap ==="

# ── 1. HF Token ────────────────────────────────────────────────────────────
if [ -z "$HF_TOKEN" ] && [ -z "$HUGGING_FACE_HUB_TOKEN" ]; then
    echo "WARNING: No HF_TOKEN set. HF Bucket features will be disabled."
    echo "Set HF_TOKEN as a Space secret to enable cloud storage."
fi

# Ensure at least one token env var is set for the app
export HF_TOKEN="${HF_TOKEN:-$HUGGING_FACE_HUB_TOKEN}"
export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"

# ── 2. Auto-create/select bucket ───────────────────────────────────────────
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

# ── 3. Pull data from bucket (if configured) ───────────────────────────────
if [ -n "$HF_TOKEN" ] && [ -f "data/hf_bucket_settings.json" ]; then
    BUCKET_ID=$(python3 -c "import json; print(json.load(open('data/hf_bucket_settings.json')).get('active_bucket_id',''))" 2>/dev/null || echo "")
    if [ -n "$BUCKET_ID" ] && [ "$BUCKET_ID" != "None" ]; then
        echo "Pulling data from bucket: $BUCKET_ID"
        # Use hf buckets sync to pull data down (if any exists)
        hf buckets sync "hf://buckets/$BUCKET_ID/uploads" "data/uploads" 2>/dev/null || echo "No remote uploads to sync (this is normal for new buckets)"
    fi
fi

# ── 4. Start ChromaDB locally (embedded) ───────────────────────────────────
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

# ── 5. Run the main app ────────────────────────────────────────────────────
echo "Starting Odysseus..."
exec "$@"

# Cleanup on exit
trap "kill $CHROMADB_PID 2>/dev/null" EXIT
