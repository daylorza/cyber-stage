export function isOriginalRequest(message: string): boolean {
  return /\b(original|unstaged)\b/i.test(message);
}

export function matchImageStyle(styles: Record<string, { image: string | null; available: boolean }>, url: string): string | null {
  const path = decodeURIComponent(url.replace(/^\/api\/media\//, ''));
  return Object.keys(styles).find(id => styles[id].available && styles[id].image === path) ?? null;
}

export function avatarState(thinking: boolean, nodding: boolean, speaking: boolean): 'idle' | 'thinking' | 'nod' | 'speaking' {
  return thinking ? 'thinking' : nodding ? 'nod' : speaking ? 'speaking' : 'idle';
}

export function mobileActions(styleId: string, roomCount: number, more: boolean): string[] {
  if (roomCount <= 1) return ['Show me Coastal', 'Show me Cyberpunk', 'Reserve it'];
  const choices = [styleId !== 'coastal' && 'Show me Coastal', styleId !== '2142' && 'Show me Cyberpunk', 'Next room'].filter((action): action is string => !!action);
  if (choices.length <= 2) return [...choices, 'Reserve it'];
  return more ? [...choices.slice(1), 'Reserve it'] : [choices[0], 'More', 'Reserve it'];
}
