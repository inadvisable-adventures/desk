const SQRT3 = Math.sqrt(3);

export type Orientation = 'pointy' | 'flat';

// angleOffset: -PI/6 for pointy-top, 0 for flat-top
export function hexPoints(cx: number, cy: number, size: number, angleOffset: number): string {
  return Array.from({ length: 6 }, (_, i) => {
    const angle = (Math.PI / 3) * i + angleOffset;
    return `${(cx + size * Math.cos(angle)).toFixed(3)},${(cy + size * Math.sin(angle)).toFixed(3)}`;
  }).join(' ');
}

// https://en.wikipedia.org/wiki/Hexagonal_Efficient_Coordinate_System
// a=0 hexes occupy the first ceil(rows/2)*cols slots; a=1 occupy the rest.
export function hecsIndex(a: number, r: number, c: number, rows: number, cols: number): number {
  return a * Math.ceil(rows / 2) * cols + r * cols + c;
}

// Pixel center for HECS coordinate (a, r, c). Works for any integer coords including negatives.
// Uses ((x % 2) + 2) % 2 for parity to handle negative values correctly in JS.
export function hexCenter(
  a: number, r: number, c: number,
  orientation: Orientation, size: number, padding: number,
): { cx: number; cy: number } {
  const row = a + 2 * r;
  const col = c;
  const rowParity = ((row % 2) + 2) % 2;
  const colParity = ((col % 2) + 2) % 2;

  if (orientation === 'flat') {
    const colSpacing = 1.5 * size;
    const rowSpacing = SQRT3 * size;
    return {
      cx: padding + size + col * colSpacing,
      cy: padding + rowSpacing * (row + 0.5) + colParity * (rowSpacing / 2),
    };
  } else {
    const colSpacing = SQRT3 * size;
    const rowSpacing = 1.5 * size;
    return {
      cx: padding + colSpacing * (col + 0.5) + rowParity * (colSpacing / 2),
      cy: padding + rowSpacing * row + size,
    };
  }
}

// Returns the HECS coords of the neighbor in direction d, or null if out of bounds.
// Pointy-top uses odd-row-right offset; flat-top uses odd-col-down offset.
// rowMin/rowMax and colMin/colMax are inclusive display row/col bounds.
export function neighborCoordsInBounds(
  a: number, r: number, c: number, d: number,
  orientation: Orientation,
  rowMin: number, rowMax: number, colMin: number, colMax: number,
): { na: number; nr: number; nc: number } | null {
  const { nrow, ncol } = computeNeighborRowCol(a, r, c, d, orientation);
  if (nrow < rowMin || nrow > rowMax || ncol < colMin || ncol > colMax) return null;
  return { na: ((nrow % 2) + 2) % 2, nr: Math.floor(nrow / 2), nc: ncol };
}

// Returns the HECS coords of the neighbor in direction d without bounds checking.
// Handles negative coordinates correctly.
export function neighborCoords(
  a: number, r: number, c: number, d: number,
  orientation: Orientation,
): { na: number; nr: number; nc: number } {
  const { nrow, ncol } = computeNeighborRowCol(a, r, c, d, orientation);
  return { na: ((nrow % 2) + 2) % 2, nr: Math.floor(nrow / 2), nc: ncol };
}

function computeNeighborRowCol(
  a: number, r: number, c: number, d: number,
  orientation: Orientation,
): { nrow: number; ncol: number } {
  const row = a + 2 * r;
  let nrow: number;
  let ncol: number;

  if (orientation === 'flat') {
    const oddCol = ((c % 2) + 2) % 2 === 1;
    const deltas: [number, number][] = oddCol
      ? [[-1, 0], [0, 1], [1, 1], [1, 0], [1, -1], [0, -1]]
      : [[-1, 0], [-1, 1], [0, 1], [1, 0], [0, -1], [-1, -1]];
    nrow = row + deltas[d]![0];
    ncol = c   + deltas[d]![1];
  } else {
    const oddRow = a === 1;
    const deltas: [number, number][] = oddRow
      ? [[-1, 1], [0, 1], [1, 1], [1, 0], [0, -1], [-1, 0]]
      : [[-1, 0], [0, 1], [1, 0], [1, -1], [0, -1], [-1, -1]];
    nrow = row + deltas[d]![0];
    ncol = c   + deltas[d]![1];
  }

  return { nrow, ncol };
}

// Cube-coordinate hex distance — admissible A* heuristic for both orientations.
export function hexDistance(
  a1: number, r1: number, c1: number,
  a2: number, r2: number, c2: number,
  orientation: Orientation,
): number {
  const row1 = a1 + 2 * r1;
  const row2 = a2 + 2 * r2;
  let cq1: number, cq2: number, cr1: number, cr2: number;
  if (orientation === 'flat') {
    cq1 = c1; cr1 = row1 - Math.floor(c1 / 2);
    cq2 = c2; cr2 = row2 - Math.floor(c2 / 2);
  } else {
    cq1 = c1 - Math.floor(row1 / 2); cr1 = row1;
    cq2 = c2 - Math.floor(row2 / 2); cr2 = row2;
  }
  const dq = Math.abs(cq1 - cq2);
  const dr = Math.abs(cr1 - cr2);
  const ds = Math.abs((-cq1 - cr1) - (-cq2 - cr2));
  return Math.max(dq, dr, ds);
}

// Expects CW-wound vertices (as produced by the hex angle formula in screen coords).
export function pointInPolygon(px: number, py: number, pts: [number, number][]): boolean {
  const n = pts.length;
  for (let i = 0; i < n; i++) {
    const [x1, y1] = pts[i]!;
    const [x2, y2] = pts[(i + 1) % n]!;
    if ((x2 - x1) * (py - y1) - (y2 - y1) * (px - x1) < 0) return false;
  }
  return true;
}
