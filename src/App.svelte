<script>
  import { onMount } from 'svelte';

  let projects = [];
  let roots = [];
  let runtimeConfig = { hostRootConfigured: false, nativeHelperSupported: false };
  let loading = true;
  let apiError = '';
  let actionError = '';
  let notice = '';
  let activeAction = '';
  let selectedProject = null;
  let restoreProject = null;
  let restorePhrase = '';
  let showInit = false;
  let showConnectGuide = false;
  let initBusy = false;
  let initError = '';
  let draggingSlug = '';
  let layout = 'grid';
  let theme = 'light';
  let initMode = 'folder';
  let folderInput;
  let folderMeta = { selected: false, folderName: '', files: [], envFile: '', envExample: '' };
  let folderDragging = false;
  let initForm = { gitUrl: '', name: '', path: '', envFile: '.env', envExample: '.env.example' };

  $: pinnedCount = projects.filter((project) => project.pinned).length;
  $: readyCount = projects.filter((project) => project.backupExists).length;

  onMount(() => {
    layout = localStorage.getItem('envshelf.layout') === 'list' ? 'list' : 'grid';
    theme = localStorage.getItem('envshelf.theme') === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = theme;
    loadProjects();
  });

  function setLayout(value) {
    layout = value;
    localStorage.setItem('envshelf.layout', value);
  }

  function toggleTheme() {
    theme = theme === 'light' ? 'dark' : 'light';
    localStorage.setItem('envshelf.theme', theme);
    document.documentElement.dataset.theme = theme;
  }

  async function loadProjects() {
    loading = true;
    apiError = '';
    try {
      const [projectsResponse, configResponse] = await Promise.all([
        fetch('/api/projects', { cache: 'no-store' }),
        fetch('/api/config', { cache: 'no-store' })
      ]);
      const projectsPayload = await projectsResponse.json();
      const configPayload = await configResponse.json();
      if (!projectsResponse.ok) throw new Error(projectsPayload.error || 'Could not load projects');
      if (!configResponse.ok) throw new Error(configPayload.error || 'Project roots are not configured');
      projects = projectsPayload.projects || [];
      roots = configPayload.allowedRoots || [];
      runtimeConfig = configPayload;
      if (selectedProject && !projects.some((project) => project.slug === selectedProject.slug)) selectedProject = null;
    } catch (error) {
      apiError = error.message || 'Dashboard API unavailable';
    } finally {
      loading = false;
    }
  }

  function openDetails(project) {
    selectedProject = project;
    actionError = '';
    notice = '';
  }

  function beginDrag(project, event) {
    draggingSlug = project.slug;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', project.slug);
  }

  async function reorderLocal(fromSlug, toSlug) {
    if (!fromSlug || fromSlug === toSlug) return;
    const from = projects.findIndex((project) => project.slug === fromSlug);
    const to = projects.findIndex((project) => project.slug === toSlug);
    if (from < 0 || to < 0) return;
    const next = [...projects];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    projects = next;
    actionError = '';
    try {
      const response = await fetch('/api/projects/reorder', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slugs: projects.map((project) => project.slug) })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Could not save order');
    } catch (error) {
      actionError = error.message || 'Could not save order';
      await loadProjects();
    }
  }

  function dropOn(project, event) {
    event.preventDefault();
    reorderLocal(draggingSlug || event.dataTransfer.getData('text/plain'), project.slug);
    draggingSlug = '';
  }

  async function togglePin(project, event) {
    event.stopPropagation();
    actionError = '';
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(project.slug)}/pin`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pinned: !project.pinned })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Could not update pin');
      projects = payload.projects || projects;
      notice = project.pinned ? 'Project unpinned.' : 'Project pinned.';
    } catch (error) {
      actionError = error.message || 'Could not update pin';
    }
  }

  async function runAction(action, project = selectedProject) {
    if (!project || activeAction) return;
    activeAction = `${action}:${project.slug}`;
    actionError = '';
    notice = '';
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(project.slug)}/${action}`, {
        method: 'POST', headers: { 'Content-Length': '0' }
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Action failed');
      notice = payload.message || 'Action completed';
      restoreProject = null;
      selectedProject = payload.project || project;
      await loadProjects();
      selectedProject = projects.find((item) => item.slug === selectedProject?.slug) || selectedProject;
    } catch (error) {
      actionError = error.message || 'Action failed';
    } finally {
      activeAction = '';
    }
  }

  function requestRestore(project = selectedProject) {
    if (!project || !project.backupExists) return;
    restoreProject = project;
    restorePhrase = '';
    actionError = '';
  }

  function confirmRestore() {
    if (restorePhrase === 'RESTORE') runAction('restore', restoreProject);
  }

  function resetInit() {
    initForm = { gitUrl: '', name: '', path: '', envFile: '.env', envExample: '.env.example' };
    folderMeta = { selected: false, folderName: '', files: [], envFile: '', envExample: '' };
    initError = '';
  }

  function openInit(mode = 'folder') {
    initMode = mode;
    resetInit();
    showInit = true;
  }

  function inspectFolderFiles(fileList) {
    const files = Array.from(fileList || []);
    const paths = files.map((file) => file.webkitRelativePath || file.name).filter(Boolean);
    const first = paths[0] || '';
    const folderName = first.includes('/') ? first.split('/')[0] : '';
    const names = [...new Set(paths.map((path) => path.split('/').pop()))];
    const envFile = names.includes('.env') ? '.env' : (names.find((name) => name.startsWith('.env.') && name !== '.env.example') || '');
    const envExample = names.includes('.env.example') ? '.env.example' : '';
    folderMeta = { selected: true, folderName, files: names.filter((name) => name.startsWith('.env')).sort(), envFile, envExample };
    initForm = {
      ...initForm,
      name: folderName,
      path: initForm.path || (roots[0] && folderName ? `${roots[0]}/${folderName}` : ''),
      envFile,
      envExample
    };
  }

  function onFolderChange(event) {
    inspectFolderFiles(event.currentTarget.files);
  }

  function onFolderDrop(event) {
    event.preventDefault();
    folderDragging = false;
    inspectFolderFiles(event.dataTransfer.files);
  }

  function dragEnter(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    folderDragging = true;
  }

  function dragLeave(event) {
    if (!event.currentTarget.contains(event.relatedTarget)) folderDragging = false;
  }

  function openNativeHelper() {
    showConnectGuide = true;
  }

  function launchConnector() {
    showConnectGuide = false;
    notice = 'If EnvShelf Connect is installed, it will open and finish the Docker connection after you approve the folder.';
    window.location.href = 'envshelf-connect://connect';
  }

  async function submitInit() {
    initBusy = true;
    initError = '';
    const endpoint = initMode === 'folder' ? '/api/projects/register' : '/api/projects/init';
    try {
      const response = await fetch(endpoint, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(initMode === 'folder' ? initForm : { ...initForm, envExample: undefined })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Could not initialize project');
      showInit = false;
      notice = payload.message || 'Project ready.';
      await loadProjects();
      selectedProject = projects.find((project) => project.slug === payload.project?.slug) || null;
    } catch (error) {
      initError = error.message || 'Could not initialize project';
    } finally {
      initBusy = false;
    }
  }

  function formatDate(value) {
    if (!value) return 'Never';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
  }

  function statusLabel(project) {
    if (project.backupExists) return 'Backup ready';
    if (project.envExists) return 'Needs backup';
    return project.status || 'Metadata only';
  }

  function hostLabel(url) {
    if (!url) return 'Local folder';
    try { return new URL(url).hostname; } catch { return 'Git remote'; }
  }
</script>

<svelte:head>
  <meta name="description" content="A local-only project shelf for encrypted environment backups." />
</svelte:head>

<div class="app-shell">
  <aside class="sidebar" aria-label="EnvShelf navigation">
    <div class="brand"><span class="brand-mark" aria-hidden="true">E</span><span><strong>EnvShelf</strong><small>local developer workspace</small></span></div>
    <div class="side-section-title"><span>Workspace</span><span class="count">{projects.length}</span></div>
    <nav class="side-nav">
      <button class="side-link active" on:click={() => loadProjects()}><span class="side-icon" aria-hidden="true">▦</span> Projects <span class="side-count">{projects.length}</span></button>
      <button class="side-link" on:click={() => openInit('folder')}><span class="side-icon" aria-hidden="true">＋</span> Add existing folder</button>
      <button class="side-link" on:click={() => openInit('clone')}><span class="side-icon" aria-hidden="true">↘</span> Clone repository</button>
    </nav>
    <div class="side-roots">
      <p>Docker-mounted roots</p>
      {#if roots.length}{#each roots as root}<code title={root}>{root}</code>{/each}{:else}<span>Not configured</span>{/if}
    </div>
    <div class="sidebar-footer"><span class="online-dot"></span><span>Loopback only</span><button class="theme-toggle" on:click={toggleTheme} aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}>{theme === 'light' ? '☾' : '☀'}</button></div>
  </aside>

  <main class="workspace">
    <header class="topbar">
      <div><p class="eyebrow">Local control plane</p><h1>Your project shelf</h1><p class="subhead">Keep every environment close, encrypted, and ready to move with you.</p></div>
      <div class="top-actions"><button class="primary-button" on:click={() => openInit('folder')}>＋ Add project</button></div>
    </header>

    {#if apiError}<div class="alert error" role="alert">{apiError}</div>{:else if actionError}<div class="alert error" role="alert">{actionError}</div>{:else if notice}<div class="alert success" role="status">{notice}</div>{/if}

    <section class="stats" aria-label="Workspace summary">
      <div><strong>{projects.length}</strong><span>Projects</span></div><div><strong>{pinnedCount}</strong><span>Pinned</span></div><div><strong>{readyCount}</strong><span>Encrypted backups</span></div>
      <div class="view-switch" role="group" aria-label="Card layout"><button class:chosen={layout === 'grid'} on:click={() => setLayout('grid')} aria-label="Grid view">▦</button><button class:chosen={layout === 'list'} on:click={() => setLayout('list')} aria-label="List view">☷</button></div>
    </section>

    {#if loading}
      <section class="card-grid" aria-label="Loading projects"><div class="project-skeleton"></div><div class="project-skeleton"></div><div class="project-skeleton"></div></section>
    {:else if projects.length}
      <div class="board-heading"><div><h2>Project shelf</h2><p>Drag any card to pin its place. Click a card for environment details.</p></div><span class="board-count">{projects.length} total</span></div>
      <section class:card-list={layout === 'list'} class="card-grid" aria-label="Projects">
        {#each projects as project (project.slug)}
          <article class:dragging={draggingSlug === project.slug} class:pinned={project.pinned} class="project-card" draggable="true" on:dragstart={(event) => beginDrag(project, event)} on:dragover={(event) => event.preventDefault()} on:drop={(event) => dropOn(project, event)} on:dragend={() => (draggingSlug = '')}>
            <div class="card-main" role="button" tabindex="0" on:click={() => openDetails(project)} on:keydown={(event) => (event.key === 'Enter' || event.key === ' ') && openDetails(project)} aria-label={`Open details for ${project.name || project.slug}`}>
              <div class="card-top"><span class="project-avatar" aria-hidden="true">{(project.name || project.slug).slice(0, 1).toUpperCase()}</span><span class="card-host">{hostLabel(project.gitUrl)}</span><button class:pinned={project.pinned} class="pin-button" on:click={(event) => togglePin(project, event)} aria-label={project.pinned ? 'Unpin project' : 'Pin project'}>{project.pinned ? '★' : '☆'}</button></div>
              <h2>{project.name || project.slug}</h2><p class="repo-url">{project.gitUrl || 'Existing local folder'}</p>
              <div class="card-path"><span aria-hidden="true">⌂</span><code>{project.path || 'Unavailable'}</code></div>
              <div class="card-foot"><span class:ready={project.backupExists} class="status-dot"></span><span>{statusLabel(project)}</span><span class="drag-hint" aria-hidden="true">⠿</span></div>
            </div>
          </article>
        {/each}
      </section>
    {:else}
      <section class="empty-state"><span class="empty-mark" aria-hidden="true">E</span><h2>Bring in your first project</h2><p>Drop an existing mounted folder or clone a repository. EnvShelf inspects names only, never secret values.</p><button class="primary-button" on:click={() => openInit('folder')}>Add existing folder</button></section>
    {/if}

    <footer class="security-note"><span aria-hidden="true">◆</span><span><strong>Metadata only.</strong> Environment values stay on disk. The browser never uploads or displays them; backups are encrypted locally.</span></footer>
  </main>
</div>

{#if selectedProject}
  <div class="modal-backdrop" role="presentation" on:click={(event) => event.target === event.currentTarget && (selectedProject = null)}>
    <div class="modal details-modal" role="dialog" aria-modal="true" aria-labelledby="details-title">
      <div class="modal-header"><div><p class="eyebrow">Project details</p><h2 id="details-title">{selectedProject.name || selectedProject.slug}</h2></div><button class="close-button" on:click={() => (selectedProject = null)} aria-label="Close details">×</button></div>
      {#if selectedProject.gitUrl}<a class="git-link" href={selectedProject.gitUrl} target="_blank" rel="noreferrer noopener">{selectedProject.gitUrl} ↗</a>{:else}<span class="git-link muted">No Git remote detected</span>{/if}
      <div class="detail-grid"><div><span>Local path</span><code>{selectedProject.path || 'Unavailable'}</code></div><div><span>Environment file</span><code>{selectedProject.envFile || '.env'}</code></div><div><span>Last backup</span><strong>{formatDate(selectedProject.lastBackup)}</strong></div><div><span>Encrypted backup</span><code>{selectedProject.backupFile || 'Not configured'}</code></div></div>
      <div class="env-section"><div class="section-heading"><div><h3>Environment keys</h3><p>One row per key. Names and state only; values remain on disk.</p></div><span class="key-count">{selectedProject.keyMetadata?.length || selectedProject.requiredKeys?.length || 0} keys</span></div>{#if selectedProject.keyMetadata?.length}<div class="key-table" aria-label="Environment key metadata"><div class="key-header"><span>Key</span><span>State</span><span>Source</span><span>Backup</span></div>{#each selectedProject.keyMetadata as item}<div class="key-row"><code>{item.name}</code><span class:configured={item.configured} class:encrypted={item.backup && item.configured} class="key-state">{item.backup && item.configured ? 'Encrypted' : item.configured ? 'Needs backup' : 'Example only'}</span><span class="key-source">{item.configured ? (selectedProject.envFile || '.env') : (selectedProject.envExample || '.env.example')}</span><span class:backup-ready={item.backup} class="key-backup">{item.backup ? 'Ready' : '—'}</span></div>{/each}</div>{:else}<div class="empty-keys">No key names found. Add an .env.example to document required configuration.</div>{/if}</div>
      <div class="modal-actions"><button class="quiet-button" disabled={activeAction !== ''} on:click={() => runAction('backup', selectedProject)}>{activeAction === `backup:${selectedProject.slug}` ? 'Backing up…' : 'Backup now'}</button><button class="danger-button" disabled={activeAction !== '' || !selectedProject.backupExists} on:click={() => requestRestore(selectedProject)}>Restore</button></div>
    </div>
  </div>
{/if}

{#if restoreProject}
  <div class="modal-backdrop above" role="presentation" on:click={(event) => event.target === event.currentTarget && (restoreProject = null)}><div class="modal confirm-modal" role="dialog" aria-modal="true" aria-labelledby="restore-title"><p class="eyebrow">Confirm restore</p><h2 id="restore-title">Replace this environment?</h2><p>The current <code>{restoreProject.envFile || '.env'}</code> is preserved beside it before restore.</p><label for="restore-confirm">Type <strong>RESTORE</strong> to continue</label><input id="restore-confirm" bind:value={restorePhrase} autocomplete="off" spellcheck="false" on:keydown={(event) => event.key === 'Enter' && confirmRestore()} /><div class="modal-actions"><button class="quiet-button" on:click={() => (restoreProject = null)}>Cancel</button><button class="danger-button" disabled={restorePhrase !== 'RESTORE' || activeAction !== ''} on:click={confirmRestore}>{activeAction ? 'Restoring…' : 'Restore environment'}</button></div></div></div>
{/if}

{#if showInit}
  <div class="modal-backdrop" role="presentation" on:click={(event) => event.target === event.currentTarget && (showInit = false)}>
    <div class="modal init-modal" role="dialog" aria-modal="true" aria-labelledby="init-title">
      <div class="modal-header"><div><p class="eyebrow">Add project</p><h2 id="init-title">Bring a workspace into EnvShelf</h2></div><button class="close-button" on:click={() => (showInit = false)} aria-label="Close add project dialog">×</button></div>
      <div class="mode-tabs" role="tablist" aria-label="Project source"><button class:chosen={initMode === 'folder'} role="tab" aria-selected={initMode === 'folder'} on:click={() => (initMode = 'folder')}>Existing folder</button><button class:chosen={initMode === 'clone'} role="tab" aria-selected={initMode === 'clone'} on:click={() => (initMode = 'clone')}>Clone Git repo</button></div>
      {#if initError}<div class="alert error" role="alert">{initError}</div>{/if}
      {#if initMode === 'folder'}
        <div class:is-dragging={folderDragging} class="drop-zone" role="region" aria-label="Drop a project folder for metadata detection" on:drop={onFolderDrop} on:dragenter={dragEnter} on:dragover={dragEnter} on:dragleave={dragLeave}><input bind:this={folderInput} class="visually-hidden" type="file" webkitdirectory directory multiple on:change={onFolderChange} /><span class="drop-icon" aria-hidden="true">↥</span><strong>{folderDragging ? 'Release to inspect this folder' : 'Drop a project folder here'}</strong><span>or <button type="button" class="inline-link" on:click={() => folderInput?.click()}>choose a folder</button></span><small>Names only: this detects `.env` files for you. It never uploads or copies secret values.</small></div>
        {#if folderMeta.selected}
          <div class="detected-note" role="status"><strong>Folder detected</strong><span>{folderMeta.folderName || 'Unnamed folder'}{folderMeta.files.length ? ` · ${folderMeta.files.join(' · ')}` : ' · No environment filenames detected'}</span></div>
          <div class="progressive-fields" aria-label="Detected project metadata">
            <div class="detected-field"><span>Project name</span><input value={folderMeta.folderName} readonly aria-readonly="true" /></div>
            {#if folderMeta.envFile}<div class="detected-field"><span>Environment file</span><input value={folderMeta.envFile} readonly aria-readonly="true" /></div>{:else}<label>Environment file<input bind:value={initForm.envFile} required placeholder=".env" /><small>Not found; enter the filename if this project uses one.</small></label>{/if}
            {#if folderMeta.envExample}<div class="detected-field"><span>Example file</span><input value={folderMeta.envExample} readonly aria-readonly="true" /></div>{:else}<label>Example file <span class="optional">optional</span><input bind:value={initForm.envExample} placeholder=".env.example" /><small>Not found; enter it if you want required keys listed.</small></label>{/if}
            <label>Git repository URL <span class="optional">optional</span><input bind:value={initForm.gitUrl} type="url" placeholder="https://github.com/you/project" /><small>Not readable from a browser folder drop; add it if known.</small></label>
          </div>
          {#if runtimeConfig.hostRootConfigured}
            <div class="mount-helper connected"><div class="mount-helper-heading"><span class="mount-status-dot"></span><strong>Docker workspace connected</strong></div><span>EnvShelf will use the detected folder under the mounted workspace.</span><div class="detected-field"><span>Mounted path</span><input value={initForm.path || 'Waiting for folder name'} readonly aria-readonly="true" /></div></div>
          {:else}
            <div class="mount-helper"><div class="mount-helper-heading"><span class="mount-status-dot"></span><strong>Docker workspace needs connection</strong></div><span>Connect a workspace root before registering. The connection flow supplies the mounted path.</span><button type="button" class="quiet-button helper-button" on:click={openNativeHelper}>Connect folder</button></div>
          {/if}
          <div class="modal-actions"><button type="button" class="quiet-button" on:click={() => (showInit = false)}>Cancel</button><button type="button" class="primary-button" on:click={submitInit} disabled={initBusy || !roots.length || !initForm.path || !initForm.envFile}>{initBusy ? 'Registering…' : 'Register folder'}</button></div>
        {/if}
      {:else}
        <p class="modal-copy">Clone a repository into one of the explicit Docker-mounted roots. Git credentials stay in your local Git helper.</p>
        <label>Git URL<input bind:value={initForm.gitUrl} required type="url" placeholder="https://github.com/you/project" /></label>
        <form on:submit|preventDefault={submitInit}><div class="form-grid"><label>Display name <span class="optional">optional</span><input bind:value={initForm.name} maxlength="120" placeholder="My project" /></label><label>Mounted path<input bind:value={initForm.path} required placeholder={roots[0] ? `${roots[0]}/my-project` : '/workspace/my-project'} /><small>Allowed roots: {roots.join(', ') || 'none configured'}</small></label></div><div class="form-grid"><label>Environment file<input bind:value={initForm.envFile} required placeholder=".env" /><small>Relative filename only.</small></label><label>Example file<input bind:value={initForm.envExample} required placeholder=".env.example" /><small>Names only; values never enter the dashboard.</small></label></div><div class="modal-actions"><button type="button" class="quiet-button" on:click={() => (showInit = false)}>Cancel</button><button class="primary-button" disabled={initBusy || !roots.length}>{initBusy ? 'Cloning…' : 'Clone & initialize'}</button></div></form>
      {/if}
    </div>
  </div>
{/if}

{#if showConnectGuide}
  <div class="modal-backdrop above" role="presentation" on:click={(event) => event.target === event.currentTarget && (showConnectGuide = false)}>
    <div class="modal helper-modal" role="dialog" aria-modal="true" aria-labelledby="connect-title">
      <div class="modal-header"><div><p class="eyebrow">Docker connection</p><h2 id="connect-title">Connect your workspace</h2></div><button class="close-button" on:click={() => (showConnectGuide = false)} aria-label="Close Docker connection guide">×</button></div>
      <p class="modal-copy">EnvShelf Connect is the optional desktop companion for Finder/Explorer drag-and-drop. It sends only safe folder metadata, asks once for the workspace scope, and creates the local ignored Compose mount.</p>
      <div class="helper-warning"><strong>Protected by design</strong><span>Environment values, private keys, and Docker socket access never leave your machine. The browser sees metadata only.</span></div>
      <div class="modal-actions"><button class="quiet-button" on:click={() => (showConnectGuide = false)}>Close</button><a class="quiet-button helper-doc-link" href="https://github.com/ychetra/envshelf/releases/latest" target="_blank" rel="noreferrer noopener">Install EnvShelf Connect ↗</a><button class="primary-button" on:click={launchConnector}>Open EnvShelf Connect</button></div>
    </div>
  </div>
{/if}
