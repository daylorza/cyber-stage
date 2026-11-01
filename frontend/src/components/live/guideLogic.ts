export function isOriginalRequest(message: string): boolean {
  return /\b(original|unstaged)\b/i.test(message);
}

export function matchImageStyle(styles: Record<string, { image: string | null; available: boolean }>, url: string): string | null {
  const path = decodeURIComponent(url.replace(/^\/api\/media\//, ''));
  return Object.keys(styles).find(id => styles[id].available && styles[id].image === path) ?? null;
}
