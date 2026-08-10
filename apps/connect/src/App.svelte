<script>
  import { onMount } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { getCurrentWebview } from '@tauri-apps/api/webview';
  import { open } from '@tauri-apps/plugin-dialog';

  let settings = { repoPath: '', dashboardUrl: 'http://127.0.0.1:8787', approvedRoots: [] };
  let metadata = null;
  let busy = false;
  let error = '';
  let notice = '';
  let dropActive = false;
  let projectPath = '';
  let missing = { name: false, envFile: false, envExample: false };
  let form = { name: '', envFile: '.env', envExample: '.env.example' };
  let standaloneRoot = '';
  let standaloneBusy = false;
  let cleanupDrop;

  onMount(() => {
    loadSettings();
    let disposed = false;
    getCurrentWebview().onDragDropEvent((event) => {
      if (event.payload.type === 'over') dropActive = true;
      if (event.payload.type === 'leave') dropActive = false;
      if (event.payload.type === 'drop') {
        dropActive = false;
        const path = event.payload.paths?.[0];
        if (path) inspect(path);
      }
    }).then((unlisten) => {
      if (disposed) unlisten(); else cleanupDrop = unlisten;
    });
    return () => { disposed = true; cleanupDrop?.(); };
  });

  async function loadSettings() {
    try { settings = await invoke('get_settings'); }
    catch (cause) { error = String(cause); }
  }

  async function chooseProject() {
    const path = await open({ directory: true, multiple: false, title: 'Choose a project folder' });
    if (typeof path === 'string') inspect(path);
  }

  async function chooseRepo() {
    const path = await open({ directory: true, multiple: false, title: 'Choose the EnvShelf repository folder' });
    if (!path) return;
    try {
      settings = await invoke('save_settings', { repoPath: path, dashboardUrl: settings.dashboardUrl });
      notice = 'EnvShelf folder saved. Drop a project to continue.';
      error = '';
    } catch (cause) { error = String(cause); }
  }

  async function chooseStandaloneRoot() {
    const path = await open({ directory: true, multiple: false, title: 'Choose your projects folder' });
    if (typeof path === 'string') standaloneRoot = path;
  }

  async function startStandalone() {
    if (!standaloneRoot || !settings.repoPath || standaloneBusy) return;
    standaloneBusy = true; error = ''; notice = '';
    try {
      const url = await invoke('start_standalone', {
        projectsRoot: standaloneRoot,
        envshelfPath: settings.repoPath || '',
        port: 8787
      });
      window.location.href = url;
    } catch (cause) { error = String(cause); standaloneBusy = false; }
  }

  async function inspect(path) {
    busy = true; error = ''; notice = '';
    try {
      projectPath = path;
      metadata = await invoke('inspect_folder', { folderPath: path });
      form = { name: metadata.name || '', envFile: metadata.envFile || '.env', envExample: metadata.envExample || '.env.example' };
      missing = { name: !metadata.name, envFile: !metadata.envFile, envExample: !metadata.envExample };
    } catch (cause) { metadata = null; error = String(cause); }
    finally { busy = false; }
  }

  function isApproved() {
    return settings.approvedRoots?.some((root) => projectPath === root || projectPath.startsWith(`${root}/`) || projectPath.startsWith(`${root}\\`));
  }

  async function connect() {
    if (!metadata || busy) return;
    busy = true; error = ''; notice = '';
    try {
      if (!settings.repoPath) throw new Error('Choose the EnvShelf source folder for Docker mode, or use Docker-free mode below.');
      const root = await invoke('parent_root', { folderPath: projectPath });
      // Tauri maps the Rust command's `request: ConnectRequest` argument by
      // name. Keep the payload nested so the desktop build and typed command
      // signature cannot drift apart.
      const request = {
        projectPath, approvedRoot: root, envshelfPath: settings.repoPath,
        projectName: form.name.trim(), envFile: form.envFile.trim(), envExample: form.envExample.trim()
      };
      const result = await invoke('connect_project', { request });
      try {
        const response = await fetch(`${settings.dashboardUrl}/api/projects/register`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: result.runtimePath, name: form.name.trim(), envFile: form.envFile.trim(), envExample: form.envExample.trim(), gitUrl: metadata.gitUrl || null })
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Docker connected, but registration failed');
        notice = 'Connected and registered. EnvShelf is ready.';
      } catch (cause) {
        notice = `Docker is connected. Open ${settings.dashboardUrl} to finish registration.`;
        error = String(cause);
      }
    } catch (cause) { error = String(cause); }
    finally { busy = false; }
  }

  function reset() { metadata = null; projectPath = ''; error = ''; notice = ''; }
</script>

<svelte:head><title>EnvShelf Connect</title></svelte:head>

<main class="shell">
  <header class="topbar">
    <div class="brand"><span class="mark">E</span><span><strong>EnvShelf</strong><small>Connect</small></span></div>
    <span class="local-pill"><i></i>Local only</span>
  </header>

  <section class="hero">
    <p class="eyebrow">ONE-CLICK PROJECT SETUP</p>
    <h1>Connect a workspace.</h1>
    <p class="lede">Drop a project folder here. EnvShelf detects its safe metadata, mounts only the approved parent folder into Docker, and registers the project.</p>
  </section>

  <section class="standalone-card">
    <div>
      <p class="eyebrow">DOCKER-FREE MODE</p>
      <h2>Open the local dashboard</h2>
      <p>Run EnvShelf directly on macOS, Windows, or Linux. Your catalog stays in app data and your projects remain in the folder you choose.</p>
    </div>
    <div class="standalone-actions">
      {#if !settings.repoPath}<button class="secondary" on:click={chooseRepo}>Choose EnvShelf folder</button>{/if}
      <button class="secondary" on:click={chooseStandaloneRoot} disabled={standaloneBusy}>{standaloneRoot ? 'Change projects folder' : 'Choose projects folder'}</button>
      {#if standaloneRoot}<span class="selected-path">{standaloneRoot}</span>{/if}
      <button class="primary" on:click={startStandalone} disabled={!standaloneRoot || standaloneBusy}>{standaloneBusy ? 'Starting…' : 'Open standalone dashboard'}</button>
    </div>
    <small>Only project metadata is shown. Secret values stay on disk and age encryption remains delegated to the official age executable.</small>
  </section>

  {#if !metadata}
    <div role="group" aria-label="Drop a project folder" class:active={dropActive} class="dropzone" on:dragover|preventDefault={() => dropActive = true} on:dragleave={() => dropActive = false}>
      <div class="drop-icon">↓</div>
      <h2>{busy ? 'Reading folder metadata…' : 'Drop a project folder'}</h2>
      <p>Nothing is uploaded. Secret values are never read.</p>
      <button class="primary" on:click={chooseProject} disabled={busy}>Choose folder</button>
    </div>
  {:else}
    <section class="workspace-card">
      <div class="card-head"><div><p class="eyebrow">PROJECT DETECTED</p><h2>{metadata.name || 'Unnamed project'}</h2></div><button class="icon-button" on:click={reset} aria-label="Choose another folder">×</button></div>
      <dl class="facts">
        <div><dt>Folder</dt><dd>{projectPath}</dd></div>
        {#if metadata.gitUrl}<div><dt>Git remote</dt><dd>{metadata.gitUrl}</dd></div>{/if}
        {#if metadata.envFiles.length}<div><dt>Environment files</dt><dd>{metadata.envFiles.join(' · ')}</dd></div>{/if}
      </dl>

      {#if missing.name}<label>Project name<input bind:value={form.name} placeholder="my-project" /></label>{/if}
      {#if missing.envFile}<label>Environment filename<input bind:value={form.envFile} placeholder=".env" /></label>{/if}
      {#if missing.envExample}<label>Example filename<input bind:value={form.envExample} placeholder=".env.example" /></label>{/if}

      <div class="connection">
        <div><span class:good={settings.repoPath} class="status-dot"></span><strong>{settings.repoPath ? 'Docker connection ready' : 'Choose EnvShelf folder once'}</strong><p>{settings.repoPath || 'The folder containing docker-compose.yml is needed to configure the local mount.'}</p></div>
        {#if !settings.repoPath}<button class="secondary" on:click={chooseRepo}>Choose EnvShelf folder</button>{/if}
      </div>
      <div class="approval"><strong>Mount scope</strong><span>{projectPath.split(/[\\/]/).slice(0, -1).join('/') || 'Project parent folder'}</span><small>Only this project’s parent folder is approved. No Docker socket and no secret values.</small></div>
      <div class="actions"><button class="secondary" on:click={reset}>Choose another</button><button class="primary" on:click={connect} disabled={busy || !settings.repoPath || !form.name.trim() || !form.envFile.trim() || !form.envExample.trim()}>{busy ? 'Connecting…' : 'Approve & connect'}</button></div>
    </section>
  {/if}

  {#if error}<div class="alert error">{error}</div>{/if}
  {#if notice}<div class="alert success">{notice}</div>{/if}

  <footer><span>EnvShelf Connect is open source</span><span>Metadata only · values stay on disk</span></footer>
</main>
