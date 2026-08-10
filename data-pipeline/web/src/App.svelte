<script>
  import { onMount } from 'svelte';
  import { post } from './lib/api.js';
  import { connect } from './lib/events.js';
  import { route } from './lib/router.svelte.js';
  import { toast } from './lib/stores.svelte.js';
  import Toast from './components/Toast.svelte';
  import Sources from './routes/Sources.svelte';
  import SourceDetail from './routes/SourceDetail.svelte';
  import Overview from './routes/Overview.svelte';
  import Export from './routes/Export.svelte';
  import Settings from './routes/Settings.svelte';

  const MENU = [
    ['sources', '#/sources', '소스'],
    ['overview', '#/overview', '현황'],
    ['export', '#/export', '학습데이터'],
    ['settings', '#/settings', '설정'],
  ];

  let syncing = $state(false);

  onMount(() => {
    const es = connect();
    return () => es.close();
  });

  async function sync() {
    syncing = true;
    try {
      await post('/api/sync');            // 결과 토스트는 SSE 가 띄운다
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      syncing = false;
    }
  }
</script>

<nav class="top">
  <b>Dr.HERi 데이터 파이프라인</b>
  <div class="right">
    <a href="http://58.229.105.3:5151" target="_blank" rel="noreferrer">FiftyOne ↗</a>
    <button class="primary" onclick={sync} disabled={syncing}>
      {syncing ? '반영 중…' : '검수결과 반영'}
    </button>
  </div>
</nav>

<div class="body">
  <aside>
    {#each MENU as [name, href, text] (name)}
      <a {href} class:active={route.name === name || (name === 'sources' && route.name === 'sourceDetail')}>{text}</a>
    {/each}
  </aside>

  <main>
    {#if route.name === 'sources'}
      <Sources />
    {:else if route.name === 'sourceDetail'}
      <SourceDetail id={route.params.id} />
    {:else if route.name === 'overview'}
      <Overview />
    {:else if route.name === 'export'}
      <Export />
    {:else if route.name === 'settings'}
      <Settings />
    {/if}
  </main>
</div>

<Toast />

<style>
  .top { display: flex; justify-content: space-between; align-items: center;
         padding: 10px 16px; border-bottom: 1px solid var(--border); }
  .right { display: flex; align-items: center; gap: 12px; }
  .right a { color: var(--muted); text-decoration: none; font-size: 12px; }
  .body { display: flex; min-height: calc(100vh - 45px); }
  aside { width: 140px; border-right: 1px solid var(--border); padding: 12px 0; }
  aside a { display: block; padding: 7px 16px; color: var(--muted); text-decoration: none; }
  aside a.active { color: var(--text); font-weight: 600; border-left: 2px solid var(--accent); }
  main { flex: 1; padding: 16px 20px; max-width: 1100px; }
</style>
