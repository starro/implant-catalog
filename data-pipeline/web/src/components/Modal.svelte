<script>
  let { title, onclose, children } = $props();
</script>

<div class="backdrop" onclick={onclose} role="presentation">
  <div class="panel" onclick={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
    <header>
      <b>{title}</b>
      <button onclick={onclose} aria-label="닫기">✕</button>
    </header>
    <div class="body">{@render children()}</div>
  </div>
</div>

<style>
  .backdrop { position: fixed; inset: 0; background: rgba(17,24,39,.35); display: flex; align-items: center; justify-content: center; z-index: 40; }
  .panel { background: #fff; border-radius: 6px; width: 520px; max-width: 92vw; max-height: 88vh; overflow: auto; }
  header { display: flex; justify-content: space-between; align-items: center; padding: 12px 14px; border-bottom: 1px solid var(--border); }
  header button { border: none; background: none; padding: 2px 6px; }
  .body { padding: 14px; }
</style>
