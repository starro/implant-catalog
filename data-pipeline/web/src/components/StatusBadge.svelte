<script>
  let { status } = $props();
  const COLOR = {
    SUCCESS: 'var(--training)',
    FAILURE: 'var(--rejected)',
    CANCELED: 'var(--rejected)',
    TIMEOUT: 'var(--rejected)',
    RUNNING: 'var(--accent)',
    QUEUED: 'var(--muted)',
  };
  const TEXT = {
    SUCCESS: '완료', FAILURE: '실패', CANCELED: '취소',
    TIMEOUT: '시간초과', RUNNING: '진행 중', QUEUED: '대기 중',
  };
</script>

<span style="color:{COLOR[status] ?? 'var(--muted)'}">{TEXT[status] ?? status ?? '—'}</span>
