<script>
  import { get } from '../lib/api.js';
  import { num } from '../lib/format.js';
  import { toast } from '../lib/stores.svelte.js';

  let dist = $state(null);

  async function load() {
    try {
      dist = await get('/api/export/summary');
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  $effect(() => { load(); });
</script>

<h2>학습데이터</h2>
<p class="label">내보내기 생성은 소스 상세 페이지에서 실행합니다. 여기서는 현황만 조회합니다.</p>

{#if dist}
  <p class="label">학습 이미지 {num(dist.total)}장</p>
  <div class="cols">
    {#each [['브랜드', dist.brands], ['모델', dist.models]] as [title, rows] (title)}
      <div>
        <h3>{title}</h3>
        <table>
          <tbody>
            {#each rows.slice(0, 20) as r (r.name)}
              <tr><td>{r.name}</td><td class="num">{num(r.count)}</td></tr>
            {/each}
          </tbody>
        </table>
        {#if rows.length > 20}<p class="label">외 {rows.length - 20}종</p>{/if}
      </div>
    {/each}
  </div>
{/if}

<style>
  h2 { font-size: 15px; margin: 0 0 12px; }
  h3 { font-size: 12px; margin: 14px 0 4px; color: var(--muted); }
  .cols { display: flex; gap: 24px; align-items: flex-start; }
  .cols > div { flex: 1; }
</style>
