/** "3 days ago". Takes milliseconds, not the API's seconds. */
export function relativeTime(ts: number): string {
  const mins = Math.round((Date.now() - ts) / 60000);
  if (mins < 2) return "a moment ago";
  if (mins < 60) return `${mins} minutes ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return hours === 1 ? "an hour ago" : `${hours} hours ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

export function groupByDate<T extends { created_at: number }>(
  items: T[]
): [string, T[]][] {
  const now = new Date();
  const startOfDay = (d: Date) =>
    new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const today = startOfDay(now);
  const yesterday = today - 86400_000;
  const weekAgo = today - 6 * 86400_000;
  const monthAgo = today - 29 * 86400_000;

  const groups = new Map<string, T[]>();
  for (const item of items) {
    const t = item.created_at * 1000;
    const label =
      t >= today
        ? "Today"
        : t >= yesterday
          ? "Yesterday"
          : t >= weekAgo
            ? "This week"
            : t >= monthAgo
              ? "This month"
              : "Older";
    const list = groups.get(label) ?? [];
    list.push(item);
    groups.set(label, list);
  }
  return Array.from(groups.entries());
}
