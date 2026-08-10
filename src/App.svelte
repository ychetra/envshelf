<script>
  import { onMount } from 'svelte';

  let projects = [];
  let selectedSlug = '';
  let loading = true;
  let apiError = '';
  let actionError = '';
  let notice = '';
  let activeAction = '';
  let restoreProject = null;
  let restorePhrase = '';

  $: selected = projects.find((project) => project.slug === selectedSlug) || projects[0] || null;

  onMount(loadProjects);

  async function loadProjects() {
    loading = true;
    apiError = '';
    try {
      const response = await fetch('/api/projects', { cache: 'no-store' });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Could not load projects');
      projects = payload.projects || [];
      if (!selectedSlug && projects[0]) selectedSlug = projects[0].slug;
      if (selectedSlug && !projects.some((project) => project.slug === selectedSlug)) {
        selectedSlug = projects[0]?.slug || '';
      }
    } catch (error) {
      apiError = error.message || 'Dashboard API unavailable';
    } finally {
      loading = false;
    }
  }

  function requestRestore() {
    if (!selected) return;
    restoreProject = selected;
    restorePhrase = '';
    actionError = '';
  }

  async function runAction(action, project = selected) {
    if (!project || activeAction) return;
    activeAction = `${action}:${project.slug}`;
    actionError = '';
    notice = '';
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(project.slug)}/${action}`, {
        method: 'POST',
        headers: { 'Content-Length': '0' }
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Action failed');
      notice = payload.message || 'Action completed';
      restoreProject = null;
      await loadProjects();
    } catch (error) {
      actionError = error.message || 'Action failed';
    } finally {
      activeAction = '';
    }
  }

  function confirmRestore() {
    if (restorePhrase === 'RESTORE') runAction('restore', restoreProject);
  }

  function formatDate(value) {
    if (!value) return 'Never';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
  }

  function statusLabel(project) {
    if (project.backupExists) return 'Backup ready';
    return project.status || 'Not backed up';
  }
</script>

<svelte:head>
  <meta name="description" content="A local-only project and encrypted environment control panel." />
</svelte:head>

<div class="shell">
  <aside class="sidebar" aria-label="Project navigation">
    <div class="brand">
      <div class="mark" aria-hidden="true">E</div>
      <div>
        <p class="brand-name">EnvShelf</p>
        <p class="brand-caption">local project control</p>
      </div>
    </div>

    <div class="sidebar-label">
      <span>Projects</span>
      <span class="count">{projects.length}</span>
    </div>
    <nav class="project-nav">
      {#if loading}
        <div class="nav-skeleton"></div>
        <div class="nav-skeleton short"></div>
      {:else if projects.length}
        {#each projects as project}
          <button class:active={selected?.slug === project.slug} class="project-link" on:click={() => (selectedSlug = project.slug)}>
            <span class="project-dot" class:ready={project.backupExists}></span>
            <span class="project-link-copy">
              <strong>{project.name || project.slug}</strong>
              <small>{statusLabel(project)}</small>
            </span>
          </button>
        {/each}
      {:else}
        <p class="sidebar-empty">No projects registered yet.</p>
      {/if}
    </nav>

    <div class="sidebar-footer">
      <span class="local-dot"></span>
      <span>Local-only</span>
    </div>
  </aside>

  <main class="content">
    <header class="topbar">
      <div>
        <p class="eyebrow">Project shelf</p>
        <h1>Environment control, kept close.</h1>
      </div>
      <button class="refresh-button" on:click={loadProjects} disabled={loading} aria-label="Refresh projects">
        <span aria-hidden="true">↻</span> Refresh
      </button>
    </header>

    {#if apiError}
      <div class="alert error" role="alert">{apiError}</div>
    {:else if actionError}
      <div class="alert error" role="alert">{actionError}</div>
    {:else if notice}
      <div class="alert success" role="status">{notice}</div>
    {/if}

    {#if loading}
      <section class="detail loading-panel" aria-label="Loading project details">
        <div class="detail-skeleton title"></div>
        <div class="detail-skeleton line"></div>
        <div class="detail-skeleton block"></div>
      </section>
    {:else if selected}
      <section class="detail" aria-labelledby="project-title">
        <div class="detail-heading">
          <div>
            <div class="status-line"><span class="status-dot" class:ready={selected.backupExists}></span>{statusLabel(selected)}</div>
            <h2 id="project-title">{selected.name || selected.slug}</h2>
            <a class="git-link" href={selected.gitUrl} target="_blank" rel="noreferrer noopener">{selected.gitUrl || 'No Git URL registered'} <span aria-hidden="true">↗</span></a>
          </div>
          <div class="actions">
            <button class="button secondary" disabled={activeAction !== ''} on:click={() => runAction('backup')}>
              {activeAction === `backup:${selected.slug}` ? 'Backing up…' : 'Backup now'}
            </button>
            <button class="button primary" disabled={activeAction !== '' || !selected.backupExists} on:click={requestRestore}>
              Restore
            </button>
          </div>
        </div>

        <div class="rule"></div>
        <div class="metadata-grid">
          <div class="metadata-item wide"><span class="metadata-label">Local path</span><code>{selected.path || 'Unavailable'}</code></div>
          <div class="metadata-item"><span class="metadata-label">Environment file</span><code>{selected.envFile || '.env'}</code></div>
          <div class="metadata-item"><span class="metadata-label">Last backup</span><span>{formatDate(selected.lastBackup)}</span></div>
          <div class="metadata-item wide"><span class="metadata-label">Encrypted backup</span><code>{selected.backupFile || 'Not configured'}</code></div>
        </div>

        <div class="env-section">
          <div class="section-title"><div><h3>Required environment keys</h3><p>Names from <code>{selected.envExample || '.env.example'}</code> only. Values stay on disk.</p></div><span class="key-count">{selected.requiredKeys?.length || 0} keys</span></div>
          {#if selected.requiredKeys?.length}
            <div class="key-list">
              {#each selected.requiredKeys as key}<code>{key}</code>{/each}
            </div>
          {:else}
            <div class="empty-keys">No keys found in the project’s example file.</div>
          {/if}
        </div>
      </section>
    {:else}
      <section class="empty-state"><div class="empty-mark">E</div><h2>Your shelf is empty.</h2><p>Register a project with the EnvShelf CLI to see its metadata here.</p><code>python3 -m app.cli register --help</code></section>
    {/if}

    <footer class="security-note"><span class="lock" aria-hidden="true">◆</span><span><strong>Metadata only.</strong> EnvShelf never displays, accepts, or stores secret values in the dashboard. Restore preserves the existing <code>.env</code> beside it first.</span></footer>
  </main>
</div>

{#if restoreProject}
  <div class="modal-backdrop" role="presentation" on:click={(event) => event.target === event.currentTarget && (restoreProject = null)}>
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="restore-title" tabindex="-1">
      <div class="modal-kicker">Confirm restore</div>
      <h2 id="restore-title">Replace {restoreProject.name || restoreProject.slug}’s environment?</h2>
      <p>The current <code>{restoreProject.envFile || '.env'}</code> will be preserved beside the file before the encrypted backup is restored.</p>
      <label for="restore-confirm">Type <strong>RESTORE</strong> to continue</label>
      <input id="restore-confirm" bind:value={restorePhrase} autocomplete="off" spellcheck="false" on:keydown={(event) => event.key === 'Enter' && confirmRestore()} />
      <div class="modal-actions"><button class="button secondary" on:click={() => (restoreProject = null)}>Cancel</button><button class="button danger" disabled={restorePhrase !== 'RESTORE' || activeAction !== ''} on:click={confirmRestore}>{activeAction ? 'Restoring…' : 'Restore environment'}</button></div>
    </div>
  </div>
{/if}
