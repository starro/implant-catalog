<script>
  import { toasts } from '../lib/stores.svelte.js';
</script>

<div class="wrap">
  {#each toasts.items as t (t.id)}
    <div class="toast {t.kind}">{t.message}</div>
  {/each}
</div>

<style>
  .wrap { position: fixed; right: 16px; bottom: 16px; display: flex; flex-direction: column; gap: 6px; z-index: 50; }
  .toast { padding: 8px 12px; border-radius: 4px; border: 1px solid var(--border); background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  .toast.success { border-left: 3px solid var(--training); }
  .toast.error { border-left: 3px solid var(--rejected); }
  .toast.info { border-left: 3px solid var(--accent); }
</style>
