export type DieSides = 2 | 4 | 6 | 8 | 10 | 12 | 20;
export const POLYHEDRAL_DICE: readonly DieSides[] = [2, 4, 6, 8, 10, 12, 20];

export function parseDiceNotation(notation: string): DieSides[] | null {
  const trimmed = notation.trim();
  if (trimmed === '') return [];
  const dice: DieSides[] = [];
  for (const part of trimmed.split(/\s*\+\s*/)) {
    const m = /^(\d+)d(\d+)$/i.exec(part.trim());
    if (!m) return null;
    const count = parseInt(m[1]!, 10);
    const sides = parseInt(m[2]!, 10);
    if (!(POLYHEDRAL_DICE as readonly number[]).includes(sides)) return null;
    for (let i = 0; i < count; i++) dice.push(sides as DieSides);
  }
  return dice;
}

// Returns probability (0–1) of each possible sum for the given dice.
export function computeDiceProbabilities(dice: readonly DieSides[]): Map<number, number> {
  let ways = new Map<number, number>([[0, 1]]);
  for (const d of dice) {
    const next = new Map<number, number>();
    for (const [sum, count] of ways) {
      for (let face = 1; face <= d; face++) {
        const s = sum + face;
        next.set(s, (next.get(s) ?? 0) + count);
      }
    }
    ways = next;
  }
  const total = dice.reduce((s, d) => s * d, 1);
  const probs = new Map<number, number>();
  for (const [sum, count] of ways) probs.set(sum, count / total);
  return probs;
}

export function formatDiceNotation(dice: readonly DieSides[]): string {
  if (dice.length === 0) return '';
  const counts = new Map<DieSides, number>();
  for (const d of dice) counts.set(d, (counts.get(d) ?? 0) + 1);
  return [...counts.entries()]
    .sort(([a], [b]) => a - b)
    .map(([sides, count]) => `${count}d${sides}`)
    .join('+');
}
