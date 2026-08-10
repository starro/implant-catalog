<script>
  import { funnelSegments, num } from '../lib/format.js';
  import { STAGE_LABELS } from './funnel_labels.js';

  let { funnel, showNumbers = true, height = 8 } = $props();
  let segments = $derived(funnelSegments(funnel));
  let tooltip = $derived(
    `단계별 현황 — 미검수 ${funnel?.unreviewed ?? 0} · 라벨 미완 ${funnel?.label_incomplete ?? 0}`,
  );
</script>

<div class="bar" style="height:{height}px" title={tooltip}>
  {#each segments as s (s.key)}
    <span style="width:{s.pct}%; background:{s.color}"></span>
  {/each}
</div>

{#if showNumbers}
  <div class="nums label">
    <span>{STAGE_LABELS.extracted} <b class="num">{num(funnel?.extracted)}</b></span>
    {#each segments as s (s.key)}
      <span style="color:{s.key === 'pending' ? 'var(--muted)' : s.color}">
        {s.label} <b class="num">{num(s.count)}</b>
      </span>
    {/each}
  </div>
{/if}

<style>
  .bar {
    display: flex;
    width: 100%;
    background: var(--pending);
    border-radius: 4px;
    overflow: hidden;
  }
  .bar span { display: block; }
  .nums { display: flex; gap: 10px; margin-top: 4px; }
</style>
