<script>
  import { onMount } from 'svelte';
  import { post } from '../lib/api.js';
  import { ENGINE_LABELS } from './engine_labels.js';
  import { engine, refreshEngineStatus, toast } from '../lib/stores.svelte.js';

  let busy = $state(false);

  onMount(() => {
    refreshEngineStatus();
    const timer = setInterval(refreshEngineStatus, 5000);   // 서버측 status 캐시(4s)와 맞춤
    return () => clearInterval(timer);
  });

  async function up() {
    busy = true;
    try {
      await post('/api/engine/up');
      await refreshEngineStatus();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }

  async function down() {
    busy = true;
    try {
      await post('/api/engine/down');
      await refreshEngineStatus();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }
</script>

<div class="engine">
  <span class="badge" class:ready={engine.status === 'ready'} class:starting={engine.status === 'starting'}>
    엔진 {ENGINE_LABELS[engine.status] ?? engine.status}
  </span>
  <button onclick={up} disabled={busy || engine.status !== 'down'}>엔진 켜기</button>
  <button onclick={down} disabled={busy || engine.status === 'down'}>엔진 끄기</button>
</div>

<style>
  .engine { display: flex; align-items: center; gap: 6px; }
  .badge { padding: 3px 9px; border-radius: 10px; font-size: 11px;
           background: var(--pending); color: var(--muted); }
  .badge.starting { background: var(--accent); color: #fff; }
  .badge.ready { background: var(--training); color: #fff; }
  .engine button { padding: 4px 9px; font-size: 12px; }
</style>
