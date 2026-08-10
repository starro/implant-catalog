<script>
  import StatusBadge from './StatusBadge.svelte';
  import { dateTime, duration, num } from '../lib/format.js';

  let { runs } = $props();
</script>

{#if runs.length === 0}
  <p class="label">수집 이력이 없습니다.</p>
{:else}
  <table>
    <thead>
      <tr><th>일시</th><th>설정</th><th>상태</th><th>완료</th><th>검출</th></tr>
    </thead>
    <tbody>
      {#each runs as r (r.id)}
        <tr>
          <td>{dateTime(r.started_at)}</td>
          <td class="label">conf {r.conf} · dpi {r.dpi} · {r.pages || '전체'}</td>
          <td>
            <StatusBadge status={r.status} />
            {#if r.error}<span class="label" title={r.error}>· {r.error.slice(0, 40)}</span>{/if}
          </td>
          <td>
            {#if r.finished_at}
              {dateTime(r.finished_at)}
              {#if duration(r.started_at, r.finished_at)}
                <span class="label">· {duration(r.started_at, r.finished_at)}</span>
              {/if}
            {:else}
              <span class="label">—</span>
            {/if}
          </td>
          <td class="num">{#if ['QUEUED', 'RUNNING'].includes(r.status)}<span class="label">진행 중</span>{:else}{num(r.extracted)}{/if}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
