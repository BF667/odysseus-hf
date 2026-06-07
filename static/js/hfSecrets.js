// static/js/hfSecrets.js — HF Spaces Secrets Management UI
// Allows viewing, adding, and deleting secrets/environment variables
// from the Odysseus Settings UI without needing .env files.

let initialized = false;
function el(id) { return document.getElementById(id); }

// API helper
async function api(method, path, body) {
  const opts = { method, credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`/api/secrets${path}`, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

// Flash message
function flash(elementId, msg, isError = false, duration = 4000) {
  const span = el(elementId);
  if (!span) return;
  span.textContent = msg;
  span.style.color = isError ? 'var(--color-error,#e06c75)' : 'var(--accent-primary,#4ec9b0)';
  span.style.opacity = '1';
  setTimeout(() => { span.style.opacity = '0.5'; span.style.color = ''; }, duration);
}

// ── Status & Rendering ──────────────────────────────────────────────────

async function loadSecretsStatus() {
  const container = el('secrets-list');
  const msgSpan = el('secrets-status-msg');
  const summaryEl = el('secrets-summary');
  const spaceBanner = el('secrets-space-banner');
  const spaceActions = el('secrets-space-actions');

  if (!container) return;

  try {
    const data = await api('GET', '/status');
    const secrets = data.secrets || [];
    const summary = data.summary || {};

    // Space banner
    if (spaceBanner) {
      if (data.is_hf_spaces) {
        spaceBanner.style.display = '';
        spaceBanner.innerHTML = `
          <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:color-mix(in srgb, var(--accent-primary,#4ec9b0) 8%, transparent);border:1px solid color-mix(in srgb, var(--accent-primary,#4ec9b0) 25%, transparent);border-radius:6px;margin-bottom:10px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary,#4ec9b0)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            <span style="font-size:11px;">Running in <strong>HF Spaces</strong> — secrets are managed via Space Settings and injected as environment variables at runtime. <code>.env</code> files are not persistent.</span>
            ${data.space_id ? `<span style="font-size:10px;opacity:0.6;margin-left:auto;">Space: ${data.space_id}</span>` : ''}
          </div>`;
      } else {
        spaceBanner.style.display = '';
        spaceBanner.innerHTML = `
          <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:color-mix(in srgb, var(--fg) 5%, transparent);border:1px solid var(--border);border-radius:6px;margin-bottom:10px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.5;"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
            <span style="font-size:11px;opacity:0.7;">Running locally — environment variables can be set via <code>.env</code> file or the form below (non-persistent).</span>
          </div>`;
      }
    }

    // Show/hide Space-only actions
    if (spaceActions) {
      spaceActions.style.display = data.is_hf_spaces ? '' : 'none';
    }

    // Summary
    if (summaryEl) {
      const requiredClass = summary.missing_required > 0 ? 'var(--color-error,#e06c75)' : 'var(--accent-primary,#4ec9b0)';
      const recClass = summary.missing_recommended > 0 ? '#f0ad4e' : 'var(--accent-primary,#4ec9b0)';
      summaryEl.innerHTML = `
        <span style="font-size:11px;">
          <strong>${summary.set}</strong>/${summary.total} configured
          ${summary.missing_required > 0 ? `<span style="color:${requiredClass};margin-left:8px;">${summary.missing_required} required missing</span>` : '<span style="color:var(--accent-primary,#4ec9b0);margin-left:8px;">All required set</span>'}
          ${summary.missing_recommended > 0 ? `<span style="color:${recClass};margin-left:8px;">${summary.missing_recommended} recommended missing</span>` : ''}
        </span>`;
    }

    // Secrets table
    const categories = { required: [], recommended: [], optional: [] };
    for (const s of secrets) {
      (categories[s.category] || categories.optional).push(s);
    }

    let html = '';

    for (const [cat, items] of Object.entries(categories)) {
      if (items.length === 0) continue;
      const catLabel = cat.charAt(0).toUpperCase() + cat.slice(1);
      const catColor = cat === 'required' ? 'var(--color-error,#e06c75)' : cat === 'recommended' ? '#f0ad4e' : 'var(--fg)';

      html += `<div style="font-size:11px;font-weight:600;margin:10px 0 4px;color:${catColor};text-transform:uppercase;letter-spacing:0.5px;">${catLabel}</div>`;

      for (const s of items) {
        const statusIcon = s.is_set
          ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary,#4ec9b0)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>'
          : '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--color-error,#e06c75)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';

        html += `
          <div style="display:flex;align-items:center;padding:5px 8px;border-bottom:1px solid var(--border);gap:8px;" data-secret-key="${s.key}">
            <div style="flex-shrink:0;">${statusIcon}</div>
            <div style="flex:1;min-width:0;">
              <div style="display:flex;align-items:center;gap:6px;">
                <code style="font-size:11px;font-weight:500;color:var(--fg);">${s.key}</code>
                ${s.is_secret ? '<span style="font-size:8px;padding:1px 3px;background:color-mix(in srgb, var(--fg) 8%, transparent);border-radius:2px;opacity:0.6;">SECRET</span>' : ''}
                ${s.hf_spaces_only ? '<span style="font-size:8px;padding:1px 3px;background:color-mix(in srgb, var(--accent-primary,#4ec9b0) 10%, transparent);border-radius:2px;color:var(--accent-primary,#4ec9b0);">HF</span>' : ''}
              </div>
              ${s.description ? `<div style="font-size:9px;opacity:0.5;margin-top:2px;">${s.description}</div>` : ''}
            </div>
            <div style="font-size:10px;opacity:0.6;flex-shrink:0;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
              ${s.is_set ? (s.is_secret ? s.value_preview : s.value_preview) : (s.default ? `<span style="opacity:0.4;">default: ${s.default}</span>` : '<span style="color:var(--color-error,#e06c75);opacity:0.5;">not set</span>')}
            </div>
            <button data-secret-edit="${s.key}" title="Set value" style="font-size:9px;padding:2px 6px;background:color-mix(in srgb, var(--accent-primary,#4ec9b0) 8%, transparent);border:1px solid color-mix(in srgb, var(--accent-primary,#4ec9b0) 25%, transparent);border-radius:3px;color:var(--accent-primary,#4ec9b0);cursor:pointer;white-space:nowrap;">Set</button>
          </div>`;
      }
    }

    container.innerHTML = html;

    // Wire "Set" buttons
    container.querySelectorAll('[data-secret-edit]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const key = btn.dataset.secretEdit;
        openSecretEditor(key);
      });
    });

  } catch (e) {
    container.innerHTML = `<div style="opacity:0.5;padding:12px;color:var(--color-error,#e06c75);">Failed to load secrets: ${e.message}</div>`;
  }
}

// ── Secret Editor Modal ─────────────────────────────────────────────────

function openSecretEditor(key) {
  const modal = el('secrets-editor-modal');
  const keyInput = el('secrets-editor-key');
  const valueInput = el('secrets-editor-value');
  const secretToggle = el('secrets-editor-is-secret');
  const msgSpan = el('secrets-editor-msg');

  if (!modal || !keyInput || !valueInput) return;

  keyInput.value = key;
  keyInput.readOnly = true;
  valueInput.value = '';
  valueInput.type = 'password';
  if (secretToggle) secretToggle.checked = true;
  if (msgSpan) msgSpan.textContent = '';

  modal.style.display = '';
  valueInput.focus();
}

function closeSecretEditor() {
  const modal = el('secrets-editor-modal');
  if (modal) modal.style.display = 'none';
}

async function saveSecret() {
  const keyInput = el('secrets-editor-key');
  const valueInput = el('secrets-editor-value');
  const secretToggle = el('secrets-editor-is-secret');
  const msgSpan = el('secrets-editor-msg');

  if (!keyInput || !valueInput) return;
  const key = keyInput.value.trim();
  const value = valueInput.value;
  const isSecret = secretToggle ? secretToggle.checked : true;

  if (!key) {
    if (msgSpan) msgSpan.textContent = 'Key is required';
    return;
  }
  if (!value) {
    if (msgSpan) msgSpan.textContent = 'Value cannot be empty';
    return;
  }

  try {
    // Try Space secret first (if in HF Spaces)
    const statusData = await api('GET', '/status');
    if (statusData.is_hf_spaces) {
      try {
        await api('POST', '/space/add', { key, value, is_secret: isSecret });
        if (msgSpan) {
          msgSpan.style.color = '#f0ad4e';
          msgSpan.textContent = 'Saved to Space secrets — restart pending';
        }
      } catch (spaceErr) {
        // Fall back to local env
        await api('POST', '/local/set', { key, value, is_secret: isSecret });
        if (msgSpan) {
          msgSpan.style.color = 'var(--accent-primary,#4ec9b0)';
          msgSpan.textContent = 'Saved to current process (non-persistent)';
        }
      }
    } else {
      // Local deployment — set in process
      await api('POST', '/local/set', { key, value, is_secret: isSecret });
      if (msgSpan) {
        msgSpan.style.color = 'var(--accent-primary,#4ec9b0)';
        msgSpan.textContent = 'Saved to current process (non-persistent)';
      }
    }

    // Refresh status after a brief delay
    setTimeout(async () => {
      await loadSecretsStatus();
      closeSecretEditor();
    }, 1500);

  } catch (e) {
    if (msgSpan) {
      msgSpan.style.color = 'var(--color-error,#e06c75)';
      msgSpan.textContent = 'Error: ' + e.message;
    }
  }
}

// ── Add Custom Secret ───────────────────────────────────────────────────

async function addCustomSecret() {
  const keyInput = el('secrets-custom-key');
  const valueInput = el('secrets-custom-value');
  const secretToggle = el('secrets-custom-is-secret');
  const msgSpan = el('secrets-custom-msg');

  if (!keyInput || !valueInput) return;
  const key = keyInput.value.trim().toUpperCase().replace(/[^A-Z0-9_]/g, '_');
  const value = valueInput.value;
  const isSecret = secretToggle ? secretToggle.checked : true;

  if (!key) {
    if (msgSpan) msgSpan.textContent = 'Key is required';
    return;
  }
  if (!value) {
    if (msgSpan) msgSpan.textContent = 'Value cannot be empty';
    return;
  }

  try {
    const statusData = await api('GET', '/status');
    if (statusData.is_hf_spaces) {
      try {
        await api('POST', '/space/add', { key, value, is_secret: isSecret });
        flash('secrets-custom-msg', 'Added to Space secrets — restart pending', false);
      } catch (spaceErr) {
        await api('POST', '/local/set', { key, value, is_secret: isSecret });
        flash('secrets-custom-msg', 'Saved to current process', false);
      }
    } else {
      await api('POST', '/local/set', { key, value, is_secret: isSecret });
      flash('secrets-custom-msg', 'Saved to current process (non-persistent)', false);
    }

    keyInput.value = '';
    valueInput.value = '';
    await loadSecretsStatus();
  } catch (e) {
    flash('secrets-custom-msg', 'Error: ' + e.message, true);
  }
}

// ── Delete Space Secret ─────────────────────────────────────────────────

async function deleteSpaceSecret(key) {
  if (!confirm(`Delete secret "${key}" from the Space? This will trigger a restart and the value will be permanently removed.`)) return;

  try {
    await api('POST', '/space/delete', { key, is_secret: true });
    flash('secrets-status-msg', `Deleted ${key} — restart pending`);
    await loadSecretsStatus();
  } catch (e) {
    flash('secrets-status-msg', 'Error: ' + e.message, true);
  }
}

// ── Refresh Space Secrets List ──────────────────────────────────────────

async function refreshSpaceSecrets() {
  const listEl = el('secrets-space-list');
  const msgSpan = el('secrets-space-msg');
  if (!listEl) return;

  try {
    const data = await api('GET', '/space/list');
    const secrets = data.secrets || [];
    if (secrets.length === 0) {
      listEl.innerHTML = '<div style="opacity:0.5;padding:8px;font-size:11px;">No Space secrets configured yet.</div>';
      return;
    }
    listEl.innerHTML = secrets.map(s => `
      <div style="display:flex;align-items:center;padding:4px 8px;border-bottom:1px solid var(--border);gap:8px;">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="${s.is_secret ? 'var(--accent-primary,#4ec9b0)' : 'var(--fg)'}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;opacity:0.6;"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        <code style="font-size:11px;flex:1;">${s.key}</code>
        ${s.is_secret ? '<span style="font-size:8px;padding:1px 3px;background:color-mix(in srgb, var(--fg) 8%, transparent);border-radius:2px;opacity:0.6;">SECRET</span>' : '<span style="font-size:8px;padding:1px 3px;background:color-mix(in srgb, var(--fg) 5%, transparent);border-radius:2px;opacity:0.4;">VAR</span>'}
        <button data-delete-space-secret="${s.key}" style="font-size:9px;padding:1px 5px;background:color-mix(in srgb, var(--color-error,#e06c75) 8%, transparent);border:1px solid color-mix(in srgb, var(--color-error,#e06c75) 25%, transparent);border-radius:3px;color:var(--color-error,#e06c75);cursor:pointer;">Delete</button>
      </div>
    `).join('');

    listEl.querySelectorAll('[data-delete-space-secret]').forEach(btn => {
      btn.addEventListener('click', () => deleteSpaceSecret(btn.dataset.deleteSpaceSecret));
    });
  } catch (e) {
    listEl.innerHTML = `<div style="opacity:0.5;padding:8px;font-size:11px;color:var(--color-error,#e06c75);">${e.message}</div>`;
  }
}

// ── Init ───────────────────────────────────────────────────────────────

export async function initHfSecrets() {
  if (initialized) return;
  initialized = true;

  // Refresh button
  const refreshBtn = el('secrets-refresh-btn');
  if (refreshBtn) refreshBtn.addEventListener('click', loadSecretsStatus);

  // Editor modal buttons
  const saveBtn = el('secrets-editor-save');
  if (saveBtn) saveBtn.addEventListener('click', saveSecret);
  const cancelBtn = el('secrets-editor-cancel');
  if (cancelBtn) cancelBtn.addEventListener('click', closeSecretEditor);

  // Toggle value visibility
  const toggleBtn = el('secrets-editor-toggle');
  const valueInput = el('secrets-editor-value');
  if (toggleBtn && valueInput) {
    toggleBtn.addEventListener('click', () => {
      valueInput.type = valueInput.type === 'password' ? 'text' : 'password';
      toggleBtn.textContent = valueInput.type === 'password' ? 'Show' : 'Hide';
    });
  }

  // Custom secret add button
  const addBtn = el('secrets-custom-add-btn');
  if (addBtn) addBtn.addEventListener('click', addCustomSecret);

  // Space secrets refresh
  const spaceRefreshBtn = el('secrets-space-refresh-btn');
  if (spaceRefreshBtn) spaceRefreshBtn.addEventListener('click', refreshSpaceSecrets);

  // Initial load
  await loadSecretsStatus();
}

window.initHfSecrets = initHfSecrets;
