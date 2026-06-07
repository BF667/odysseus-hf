// static/js/githubRepos.js — GitHub OAuth & Repository Management UI
// Follows the same pattern as hfBuckets.js

let initialized = false;
function el(id) { return document.getElementById(id); }

// Centralized API helper
async function api(method, path, body) {
  const opts = { method, credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`/api/github${path}`, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

// Show a temporary message near an element
function flash(elementId, msg, duration = 3000) {
  const span = el(elementId);
  if (!span) return;
  span.textContent = msg;
  span.style.opacity = '1';
  setTimeout(() => { span.style.opacity = '0.5'; }, duration);
}

// ── Status & Auth ──────────────────────────────────────────────────────

async function loadStatus() {
  try {
    const data = await api('GET', '/status');
    const configCard = el('gh-config-card');
    const userInfo = el('gh-user-info');
    const authSection = el('gh-auth-section');
    const connectedSection = el('gh-connected-section');

    if (data.authenticated && data.user) {
      // Show connected state
      if (authSection) authSection.style.display = 'none';
      if (connectedSection) connectedSection.style.display = '';
      if (userInfo) {
        userInfo.innerHTML = `
          <div style="display:flex;align-items:center;gap:8px;">
            ${data.user.avatar_url ? `<img src="${data.user.avatar_url}" style="width:24px;height:24px;border-radius:50%;">` : ''}
            <span style="font-weight:500;">${data.user.name || data.user.login}</span>
            <a href="${data.user.html_url}" target="_blank" rel="noopener" style="font-size:11px;opacity:0.7;">@${data.user.login}</a>
          </div>
        `;
        userInfo.style.display = '';
      }
      if (configCard) { configCard.style.opacity = '1'; configCard.style.pointerEvents = 'auto'; }
      // Load repos
      await refreshRepoList();
      // Load rate limit
      await loadRateLimit();
    } else if (data.configured) {
      // OAuth app configured but not connected
      if (authSection) authSection.style.display = '';
      if (connectedSection) connectedSection.style.display = 'none';
      if (configCard) { configCard.style.opacity = '0.5'; configCard.style.pointerEvents = 'none'; }
      if (userInfo) userInfo.style.display = 'none';
    } else {
      // Not configured
      if (authSection) authSection.style.display = '';
      if (connectedSection) connectedSection.style.display = 'none';
      if (configCard) { configCard.style.opacity = '0.5'; configCard.style.pointerEvents = 'none'; }
      if (userInfo) userInfo.style.display = 'none';
    }
  } catch (e) {
    console.warn('Failed to load GitHub status:', e);
  }
}

async function startOAuth() {
  try {
    const data = await api('GET', '/oauth/authorize');
    if (data.url) {
      window.open(data.url, '_blank', 'width=600,height=700');
    }
  } catch (e) {
    flash('gh-auth-msg', 'Error: ' + e.message);
  }
}

async function disconnectGitHub() {
  if (!confirm('Disconnect your GitHub account? The stored token will be removed.')) return;
  try {
    await api('POST', '/oauth/disconnect');
    flash('gh-connected-msg', 'Disconnected');
    await loadStatus();
  } catch (e) {
    flash('gh-connected-msg', 'Error: ' + e.message);
  }
}

// ── Repositories ──────────────────────────────────────────────────────

async function refreshRepoList(owner) {
  const list = el('gh-repos-list');
  const msgSpan = el('gh-repos-msg');
  if (!list) return;

  try {
    const params = new URLSearchParams();
    if (owner) params.set('owner', owner);
    params.set('per_page', '30');
    params.set('sort', 'updated');

    const data = await api('GET', `/repos?${params}`);
    const repos = data.repos || [];

    if (repos.length === 0) {
      list.innerHTML = '<div style="opacity:0.5;padding:12px;">No repositories found.</div>';
      return;
    }

    list.innerHTML = repos.map(r => `
      <div style="display:flex;align-items:center;padding:6px 8px;border-bottom:1px solid var(--border);gap:8px;cursor:pointer;" data-gh-repo="${r.full_name}">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;opacity:0.5;"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
        <div style="flex:1;min-width:0;">
          <div style="display:flex;align-items:center;gap:6px;">
            <a href="${r.html_url}" target="_blank" rel="noopener" style="font-size:12px;font-weight:500;color:var(--brand-color,var(--red,#e06c75));text-decoration:none;">${r.full_name}</a>
            ${r.private ? '<span style="font-size:9px;padding:1px 4px;border:1px solid var(--border);border-radius:3px;opacity:0.6;">Private</span>' : '<span style="font-size:9px;padding:1px 4px;border:1px solid var(--border);border-radius:3px;opacity:0.6;color:var(--accent-primary,#4ec9b0);">Public</span>'}
          </div>
          ${r.description ? `<div style="font-size:10px;opacity:0.5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${r.description}</div>` : ''}
        </div>
        <div style="display:flex;gap:8px;font-size:10px;opacity:0.5;flex-shrink:0;">
          ${r.language ? `<span>${r.language}</span>` : ''}
          <span title="Stars">★${r.stargazers_count}</span>
        </div>
        <button class="admin-btn-add" data-gh-delete-repo="${r.full_name}" style="font-size:10px;padding:2px 6px;background:color-mix(in srgb, var(--color-error,#e06c75) 10%, transparent);border:1px solid var(--color-error,#e06c75);border-radius:4px;color:var(--color-error,#e06c75);white-space:nowrap;">Delete</button>
      </div>
    `).join('');

    // Wire delete buttons
    list.querySelectorAll('[data-gh-delete-repo]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const fullName = btn.dataset.ghDeleteRepo;
        if (!confirm(`Delete repository "${fullName}"? This is IRREVERSIBLE! Type "${fullName}" to confirm.`)) return;
        try {
          await api('DELETE', `/repos/${fullName}?confirm=${encodeURIComponent(fullName)}`);
          flash('gh-repos-msg', `Deleted ${fullName}`);
          await refreshRepoList(owner);
        } catch (err) {
          flash('gh-repos-msg', 'Error: ' + err.message);
        }
      });
    });

  } catch (e) {
    list.innerHTML = `<div style="opacity:0.5;padding:12px;color:var(--color-error,#e06c75);">Failed to load repos: ${e.message}</div>`;
  }
}

async function createRepo() {
  const nameInput = el('gh-new-repo-name');
  const descInput = el('gh-new-repo-desc');
  const privateCheck = el('gh-new-repo-private');
  const msgSpan = el('gh-repo-msg');

  if (!nameInput || !nameInput.value.trim()) {
    if (msgSpan) msgSpan.textContent = 'Repository name is required';
    return;
  }

  try {
    await api('POST', '/repos', {
      name: nameInput.value.trim(),
      description: (descInput?.value || '').trim(),
      private: privateCheck?.checked ?? true,
      auto_init: true,
    });
    if (msgSpan) msgSpan.textContent = 'Repository created!';
    nameInput.value = '';
    if (descInput) descInput.value = '';
    await refreshRepoList();
  } catch (e) {
    if (msgSpan) msgSpan.textContent = 'Error: ' + e.message;
  }
}

// ── Rate Limit ─────────────────────────────────────────────────────────

async function loadRateLimit() {
  const el_ = el('gh-rate-limit');
  if (!el_) return;
  try {
    const data = await api('GET', '/rate-limit');
    const pct = data.limit > 0 ? Math.round((data.remaining / data.limit) * 100) : 0;
    const color = pct > 50 ? 'var(--accent-primary,#4ec9b0)' : pct > 20 ? '#f0ad4e' : 'var(--color-error,#e06c75)';
    const resetDate = data.reset ? new Date(data.reset * 1000).toLocaleTimeString() : 'unknown';
    el_.innerHTML = `<span style="color:${color}">${data.remaining}/${data.limit}</span> requests remaining <span style="opacity:0.5">(resets ${resetDate})</span>`;
  } catch (_) {
    el_.textContent = '';
  }
}

// ── Publish Project ────────────────────────────────────────────────────

async function publishProject() {
  const repoNameInput = el('gh-publish-repo-name');
  const msgSpan = el('gh-publish-msg');
  if (!repoNameInput || !repoNameInput.value.trim()) {
    if (msgSpan) msgSpan.textContent = 'Repository name is required';
    return;
  }

  const repoName = repoNameInput.value.trim();
  if (!confirm(`Publish Odysseus project to "${repoName}"? This will create a new GitHub repository and push configuration files.`)) return;

  try {
    // Step 1: Create the repo
    if (msgSpan) msgSpan.textContent = 'Creating repository...';
    const createResult = await api('POST', '/repos', {
      name: repoName,
      description: 'My Odysseus AI workspace configuration',
      private: true,
      auto_init: true,
    });

    const owner = createResult.repo.full_name.split('/')[0];
    const repo = createResult.repo.name;

    // Step 2: Push a README about the project
    if (msgSpan) msgSpan.textContent = 'Pushing project files...';
    const readmeContent = `# ${repoName}\n\nMy Odysseus AI workspace configuration, published from [Odysseus](https://github.com/BF667/odysseus-hf).\n\n## Setup\n\nThis repository contains Odysseus workspace settings. Clone it and use with your local Odysseus instance.\n`;
    await api('POST', '/files/push', {
      owner: owner,
      repo: repo,
      path: 'README.md',
      content: readmeContent,
      message: 'Initial commit from Odysseus',
      branch: 'main',
    });

    if (msgSpan) msgSpan.textContent = `Published to ${createResult.repo.html_url}`;
    repoNameInput.value = '';
    await refreshRepoList();
  } catch (e) {
    if (msgSpan) msgSpan.textContent = 'Error: ' + e.message;
  }
}

// ── Init ───────────────────────────────────────────────────────────────

export async function initGithubRepos() {
  if (initialized) return;
  initialized = true;

  // OAuth connect button
  const connectBtn = el('gh-auth-connect');
  if (connectBtn) connectBtn.addEventListener('click', startOAuth);

  // Disconnect button
  const disconnectBtn = el('gh-disconnect-btn');
  if (disconnectBtn) disconnectBtn.addEventListener('click', disconnectGitHub);

  // Create repo button
  const createBtn = el('gh-create-repo-btn');
  if (createBtn) createBtn.addEventListener('click', createRepo);

  // Refresh repos button
  const refreshBtn = el('gh-refresh-repos-btn');
  if (refreshBtn) refreshBtn.addEventListener('click', () => refreshRepoList());

  // Publish project button
  const publishBtn = el('gh-publish-btn');
  if (publishBtn) publishBtn.addEventListener('click', publishProject);

  // Check for OAuth callback result in URL
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('github_auth') === 'success') {
    // Clean URL
    const cleanUrl = new URL(window.location);
    cleanUrl.searchParams.delete('github_auth');
    cleanUrl.searchParams.delete('msg');
    window.history.replaceState({}, '', cleanUrl);
  }

  // Initial load
  await loadStatus();
}

window.initGithubRepos = initGithubRepos;
