// static/js/hfBuckets.js — Hugging Face Storage Bucket management module (ES6)
// Integrates into the Settings panel under the "Cloud Storage" tab.

let initialized = false;

function el(id) { return document.getElementById(id); }

/* ── API helpers ── */

async function api(method, path, body) {
  const opts = {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`/api/buckets${path}`, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

/* ── Format helpers ── */

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
}

/* ── Load bucket status ── */

async function loadStatus() {
  try {
    const status = await api('GET', '/status');
    const configCard = el('set-bucket-config-card');
    const statusCard = el('set-bucket-status-card');
    const filesCard = el('set-bucket-files-card');
    const dangerCard = el('set-bucket-danger-card');
    const userInfo = el('set-bucket-user-info');
    const activeInfo = el('set-bucket-active-info');

    // Show user info
    if (status.has_token && status.user) {
      userInfo.style.display = '';
      userInfo.textContent = `Logged in as @${status.user.name}` +
        (status.user.organizations && status.user.organizations.length > 0
          ? ` (orgs: ${status.user.organizations.join(', ')})`
          : '');
      // Enable config card
      if (configCard) {
        configCard.style.opacity = '';
        configCard.style.pointerEvents = '';
      }
    } else if (status.has_token) {
      userInfo.style.display = '';
      userInfo.textContent = 'Token saved (user info unavailable)';
      if (configCard) {
        configCard.style.opacity = '';
        configCard.style.pointerEvents = '';
      }
    } else {
      userInfo.style.display = '';
      userInfo.textContent = 'No token configured. Set your HF token above to get started.';
      if (configCard) {
        configCard.style.opacity = '0.5';
        configCard.style.pointerEvents = 'none';
      }
    }

    // Show active bucket info
    if (status.active_bucket_id) {
      activeInfo.style.display = '';
      activeInfo.innerHTML = `<strong>Active:</strong> ${status.active_bucket_id}`;
      statusCard.style.display = '';
      filesCard.style.display = '';
      dangerCard.style.display = '';
      loadBucketInfo(status.active_bucket_id);
      loadBucketFiles();
    } else {
      activeInfo.style.display = '';
      activeInfo.textContent = 'No bucket selected. Create a new one or select an existing one below.';
      statusCard.style.display = 'none';
      filesCard.style.display = 'none';
      dangerCard.style.display = 'none';
    }

    return status;
  } catch (e) {
    console.warn('[hfBuckets] Failed to load status:', e);
    return null;
  }
}

/* ── Load bucket info ── */

async function loadBucketInfo(bucketId) {
  try {
    const info = await api('GET', `/info/${bucketId}`);
    const content = el('set-bucket-status-content');
    if (content) {
      content.innerHTML = `
        <div class="settings-row" style="gap:16px;flex-wrap:wrap;">
          <div><strong>Bucket:</strong> ${info.id}</div>
          <div><strong>Visibility:</strong> ${info.private ? 'Private' : 'Public'}</div>
          <div><strong>Size:</strong> ${formatBytes(info.size)}</div>
          <div><strong>Files:</strong> ${info.total_files || 0}</div>
          <div><strong>Created:</strong> ${info.created_at ? new Date(info.created_at).toLocaleDateString() : 'Unknown'}</div>
        </div>
      `;
    }
  } catch (e) {
    console.warn('[hfBuckets] Failed to load bucket info:', e);
  }
}

/* ── Load bucket files ── */

async function loadBucketFiles() {
  try {
    const data = await api('GET', '/files?recursive=true');
    const list = el('set-bucket-files-list');
    if (!list) return;
    const files = data.files || [];
    if (files.length === 0) {
      list.innerHTML = '<div style="opacity:0.5;padding:8px;">No files in bucket yet. Upload files or sync your uploads to populate this bucket.</div>';
      return;
    }
    list.innerHTML = files.map(f => {
      const icon = f.type === 'directory' ? '📁' : '📄';
      return `<div style="padding:3px 6px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;">
        <span>${icon} ${f.path}</span>
        <span style="opacity:0.5;">${f.type === 'file' ? formatBytes(f.size) : ''}</span>
      </div>`;
    }).join('');
  } catch (e) {
    console.warn('[hfBuckets] Failed to load files:', e);
  }
}

/* ── List buckets for selector ── */

async function refreshBucketList() {
  const select = el('set-bucket-select');
  if (!select) return;
  try {
    const data = await api('GET', '/list');
    const buckets = data.buckets || [];
    // Keep current value
    const current = select.value;
    select.innerHTML = '<option value="">No bucket selected</option>';
    buckets.forEach(b => {
      const opt = document.createElement('option');
      opt.value = b.id;
      opt.textContent = `${b.id} (${formatBytes(b.size)}, ${b.total_files || 0} files${b.private ? ', private' : ''})`;
      select.appendChild(opt);
    });
    if (current && Array.from(select.options).some(o => o.value === current)) {
      select.value = current;
    }
  } catch (e) {
    console.warn('[hfBuckets] Failed to list buckets:', e);
  }
}

/* ── Init ── */

export async function initBucketSettings() {
  if (initialized) return;
  initialized = true;

  // Token save
  const tokenSave = el('set-bucket-token-save');
  const tokenInput = el('set-bucket-token');
  if (tokenSave && tokenInput) {
    tokenSave.addEventListener('click', async () => {
      const token = tokenInput.value.trim();
      if (!token) return;
      tokenSave.textContent = 'Saving...';
      tokenSave.disabled = true;
      try {
        const result = await api('POST', '/token', { token });
        tokenInput.value = '';
        tokenSave.textContent = 'Saved!';
        setTimeout(() => { tokenSave.textContent = 'Save Token'; tokenSave.disabled = false; }, 2000);
        await loadStatus();
        await refreshBucketList();
      } catch (e) {
        tokenSave.textContent = 'Error';
        setTimeout(() => { tokenSave.textContent = 'Save Token'; tokenSave.disabled = false; }, 2000);
        alert('Failed to save token: ' + e.message);
      }
    });
  }

  // Select bucket
  const selectBtn = el('set-bucket-select-btn');
  if (selectBtn) {
    selectBtn.addEventListener('click', async () => {
      const select = el('set-bucket-select');
      const bucketId = select ? select.value : '';
      if (!bucketId) { alert('Please select a bucket first.'); return; }
      selectBtn.textContent = 'Selecting...';
      selectBtn.disabled = true;
      try {
        await api('POST', '/select', { bucket_id: bucketId });
        selectBtn.textContent = 'Selected!';
        setTimeout(() => { selectBtn.textContent = 'Select'; selectBtn.disabled = false; }, 2000);
        await loadStatus();
      } catch (e) {
        selectBtn.textContent = 'Error';
        setTimeout(() => { selectBtn.textContent = 'Select'; selectBtn.disabled = false; }, 2000);
        alert('Failed to select bucket: ' + e.message);
      }
    });
  }

  // Create bucket
  const createBtn = el('set-bucket-create-btn');
  if (createBtn) {
    createBtn.addEventListener('click', async () => {
      const nameInput = el('set-bucket-new-name');
      const privateCheck = el('set-bucket-new-private');
      const name = nameInput ? nameInput.value.trim() : '';
      if (!name) { alert('Please enter a bucket name.'); return; }
      if (!/^[a-zA-Z0-9_-]+$/.test(name)) { alert('Bucket name can only contain letters, numbers, hyphens, and underscores.'); return; }
      createBtn.textContent = 'Creating...';
      createBtn.disabled = true;
      try {
        const result = await api('POST', '/create', {
          name,
          private: privateCheck ? privateCheck.checked : true,
        });
        createBtn.textContent = 'Created!';
        if (nameInput) nameInput.value = '';
        setTimeout(() => { createBtn.textContent = 'Create'; createBtn.disabled = false; }, 2000);
        // Auto-select the new bucket
        if (result.bucket && result.bucket.id) {
          await api('POST', '/select', { bucket_id: result.bucket.id });
        }
        await loadStatus();
        await refreshBucketList();
      } catch (e) {
        createBtn.textContent = 'Error';
        setTimeout(() => { createBtn.textContent = 'Create'; createBtn.disabled = false; }, 2000);
        alert('Failed to create bucket: ' + e.message);
      }
    });
  }

  // Sync uploads
  const syncBtn = el('set-bucket-sync-btn');
  if (syncBtn) {
    syncBtn.addEventListener('click', async () => {
      syncBtn.textContent = 'Syncing...';
      syncBtn.disabled = true;
      const msg = el('set-bucket-files-msg');
      try {
        const result = await api('POST', '/sync-uploads');
        if (msg) { msg.textContent = 'Sync complete!'; msg.style.color = 'var(--fg)'; }
        setTimeout(() => { if (msg) msg.textContent = ''; }, 3000);
        await loadBucketFiles();
        await loadBucketInfo(el('set-bucket-active-info')?.textContent?.replace('Active: ', '') || '');
      } catch (e) {
        if (msg) { msg.textContent = 'Sync failed: ' + e.message; msg.style.color = 'var(--red)'; }
      } finally {
        syncBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Sync Uploads to Bucket`;
        syncBtn.disabled = false;
      }
    });
  }

  // Refresh files
  const refreshBtn = el('set-bucket-refresh-btn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.textContent = 'Loading...';
      refreshBtn.disabled = true;
      await loadBucketFiles();
      refreshBtn.textContent = 'Refresh Files';
      refreshBtn.disabled = false;
    });
  }

  // Disconnect
  const disconnectBtn = el('set-bucket-disconnect-btn');
  if (disconnectBtn) {
    disconnectBtn.addEventListener('click', async () => {
      if (!confirm('Disconnect cloud storage? Local files will be preserved but new uploads will not be synced to the cloud.')) return;
      try {
        await api('POST', '/clear');
        await loadStatus();
        await refreshBucketList();
      } catch (e) {
        alert('Failed to disconnect: ' + e.message);
      }
    });
  }

  // Initial load
  await loadStatus();
  await refreshBucketList();
}

// Expose globally for the settings module
window.initBucketSettings = initBucketSettings;
