import dayjs from 'dayjs';

export function formatDate(date?: string | null): string {
  return date ? dayjs(date).format('YYYY-MM-DD HH:mm') : '-';
}

export function formatDuration(ms?: number | null): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return '-';
  if (ms < 0) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}min`;
}

export function formatPercent(n: number, d: number): string {
  if (d === 0) return '-';
  return `${((n / d) * 100).toFixed(1)}%`;
}
