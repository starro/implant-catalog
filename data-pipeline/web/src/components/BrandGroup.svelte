<script>
  import FunnelBar from './FunnelBar.svelte';
  import { dateTime, num } from '../lib/format.js';

  let { group } = $props();
  let open = $state(true);
</script>

<section>
  <button class="head" onclick={() => (open = !open)}>
    <span class="caret">{open ? '▾' : '▸'}</span>
    <b>{group.brand}</b>
    <span class="label">문서 {group.documents.length}</span>
    <span class="bar"><FunnelBar funnel={group.funnel} showNumbers={false} height={6} /></span>
    <span class="label num">
      추출 {num(group.funnel.extracted)} · 학습 {num(group.funnel.training)}
      · 버림 {num(group.funnel.rejected)} · 대기 {num(group.funnel.pending)}
    </span>
  </button>

  {#if open}
    <table>
      <thead>
        <tr><th>문서</th><th style="width:180px">퍼널</th><th style="width:130px">마지막 수집</th></tr>
      </thead>
      <tbody>
        {#each group.documents as d (d.id)}
          <tr>
            <td><a href="#/sources/{d.id}">{d.name}</a> <span class="label">{d.url}</span></td>
            <td>
              <FunnelBar funnel={d.funnel} showNumbers={false} height={6} />
              <span class="label num">
                {num(d.funnel.extracted)} / {num(d.funnel.training)} /
                {num(d.funnel.rejected)} / {num(d.funnel.pending)}
              </span>
            </td>
            <td class="label">{dateTime(d.last_run_at)} {d.last_run_status ?? ''}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<style>
  section { margin-bottom: 18px; }
  .head { display: flex; align-items: center; gap: 8px; width: 100%; border: none;
          background: none; padding: 6px 0; text-align: left; }
  .caret { color: var(--muted); }
  .bar { flex: 0 0 160px; }
  td a { color: var(--text); }
  td .label { margin-left: 6px; }
</style>
