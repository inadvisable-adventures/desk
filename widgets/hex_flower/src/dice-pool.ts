import type { RegisterSignalSenderDetail, RegisterDatastoreDetail } from './signal.types.js';
import { type DieSides, POLYHEDRAL_DICE, parseDiceNotation, formatDiceNotation } from './dice-utils.js';

export type { DieSides } from './dice-utils.js';
export { parseDiceNotation, formatDiceNotation } from './dice-utils.js';

// [front face color, shadow/edge color]
const DIE_COLORS: Record<DieSides, [string, string]> = {
  2:  ['#94a3b8', '#334155'],
  4:  ['#ef4444', '#7f1d1d'],
  6:  ['#3b82f6', '#1e3a8a'],
  8:  ['#f97316', '#7c2d12'],
  10: ['#22c55e', '#14532d'],
  12: ['#a855f7', '#3b0764'],
  20: ['#eab308', '#713f12'],
};

// ── Geometry ──────────────────────────────────────────────────────────────

interface Point { x: number; y: number }

function regularPoly(n: number, cx: number, cy: number, r: number, startAngle: number): Point[] {
  return Array.from({ length: n }, (_, i) => {
    const a = startAngle + (2 * Math.PI / n) * i;
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  });
}

// Returns the front-face polygon for a die centered at (cx,cy) with circumradius r.
// All polygons are clockwise in screen coords (Y-down).
function dieFrontPoints(sides: DieSides, cx: number, cy: number, r: number): Point[] {
  switch (sides) {
    case 2:  return regularPoly(32, cx, cy, r, 0);
    case 4:  return regularPoly(3, cx, cy, r, -Math.PI / 2);
    case 6: {
      const h = r * 0.9;
      return [
        { x: cx - h, y: cy - h }, { x: cx + h, y: cy - h },
        { x: cx + h, y: cy + h }, { x: cx - h, y: cy + h },
      ];
    }
    case 8:  return regularPoly(4, cx, cy, r, -Math.PI / 2);
    case 10: return [
      { x: cx,           y: cy - r          },
      { x: cx + r * 0.9, y: cy + r * 0.15  },
      { x: cx,           y: cy + r * 0.55  },
      { x: cx - r * 0.9, y: cy + r * 0.15  },
    ];
    case 12: return regularPoly(5, cx, cy, r, -Math.PI / 2);
    case 20: return regularPoly(3, cx, cy, r, Math.PI / 2);
  }
}

// Returns the visible side-face quads when the front face is extruded by (dx,dy).
// A side is visible when dot(outward_normal, extrusion) > 0.
function extrudedSides(front: Point[], dx: number, dy: number): Array<[Point, Point, Point, Point]> {
  const n = front.length;
  const back: Point[] = front.map(p => ({ x: p.x + dx, y: p.y + dy }));
  const faces: Array<[Point, Point, Point, Point]> = [];
  for (let i = 0; i < n; i++) {
    const a = front[i]!;
    const b = front[(i + 1) % n]!;
    const nx = b.y - a.y;
    const ny = a.x - b.x;
    if (nx * dx + ny * dy > 0) {
      faces.push([a, b, back[(i + 1) % n]!, back[i]!]);
    }
  }
  return faces;
}

function ptsStr(pts: readonly Point[]): string {
  return pts.map(p => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ');
}

// ── SVG icon builders ─────────────────────────────────────────────────────

// Flat 2D icon for palette buttons — filled polygon with "d{n}" label overlay.
function palette2DSvg(sides: DieSides, size: number): string {
  const [front, dark] = DIE_COLORS[sides];
  const cx = size / 2, cy = size / 2, r = size * 0.42;
  const attrs = `fill="${front}" stroke="${dark}" stroke-width="1.5"`;
  const label = `<text x="${cx}" y="${cy}" class="palette-label">d${sides}</text>`;
  if (sides === 2) {
    return `<circle cx="${cx}" cy="${cy}" r="${r}" ${attrs}/>${label}`;
  }
  return `<polygon points="${ptsStr(dieFrontPoints(sides, cx, cy, r))}" ${attrs}/>${label}`;
}

// 3D extruded icon for pool dice. displayNum defaults to sides (the max) when no roll result.
function pool3DSvg(sides: DieSides, size: number, displayNum: number = sides): string {
  const [front, dark] = DIE_COLORS[sides];
  const cx = size * 0.43, cy = size * 0.43, r = size * 0.36;
  const dx = size * 0.13, dy = size * 0.13;
  const label = `<text x="${cx.toFixed(1)}" y="${cy.toFixed(1)}" class="pool-number">${displayNum}</text>`;

  if (sides === 2) {
    return (
      `<circle cx="${(cx + dx).toFixed(2)}" cy="${(cy + dy).toFixed(2)}" r="${r.toFixed(2)}" fill="${dark}" stroke="${dark}" stroke-width="0.5"/>` +
      `<circle cx="${cx.toFixed(2)}" cy="${cy.toFixed(2)}" r="${r.toFixed(2)}" fill="${front}" stroke="${dark}" stroke-width="1.5"/>` +
      label
    );
  }

  const frontPts = dieFrontPoints(sides, cx, cy, r);
  const sideFaces = extrudedSides(frontPts, dx, dy);
  const backPts = frontPts.map(p => ({ x: p.x + dx, y: p.y + dy }));

  return (
    `<polygon points="${ptsStr(backPts)}" fill="${dark}" stroke="${dark}" stroke-width="0.5"/>` +
    sideFaces.map(f => `<polygon points="${ptsStr(f)}" fill="${dark}" stroke="${dark}" stroke-width="0.5"/>`).join('') +
    `<polygon points="${ptsStr(frontPts)}" fill="${front}" stroke="${dark}" stroke-width="1.5"/>` +
    label
  );
}

// ── HTML element builders ─────────────────────────────────────────────────

function poolDieHtml(sides: DieSides, index: number, editMode: boolean, rollResult: number | null): string {
  const size = 52;
  return (
    `<svg class="pool-die${editMode ? ' removable' : ''}"` +
    ` data-index="${index}" data-sides="${sides}"` +
    ` width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">` +
    pool3DSvg(sides, size, rollResult ?? undefined) +
    `</svg>`
  );
}

function paletteDieHtml(sides: DieSides): string {
  const size = 48;
  return (
    `<button class="palette-btn" data-sides="${sides}">` +
    `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">` +
    palette2DSvg(sides, size) +
    `</svg></button>`
  );
}

// ── Web Component ─────────────────────────────────────────────────────────

class DicePool extends HTMLElement {
  private dice: DieSides[] = [];
  private _editMode = false;
  private rollResults: number[] = [];
  private sendSignal: ((message: string) => void) | null = null;
  private disconnectSignal: (() => void) | null = null;
  private sendChangedSignal: ((message: string) => void) | null = null;
  private disconnectChangedSignal: (() => void) | null = null;

  static get observedAttributes(): string[] {
    return ['dice-notation'];
  }

  // Allow parent components to control edit mode without an independent toggle.
  set editMode(val: boolean) {
    this._editMode = val;
    this.rollResults = [];
    if (this.shadowRoot !== null) this.updateView();
  }

  connectedCallback(): void {
    this.attachShadow({ mode: 'open' });
    const shadow = this.shadowRoot!;
    const tpl = document.getElementById('dice-pool') as HTMLTemplateElement;
    shadow.appendChild(tpl.content.cloneNode(true));
    this.dice = parseDiceNotation(this.getAttribute('dice-notation') ?? '') ?? [];
    this.wireEvents();
    this.updateView();

    if (!this.hasAttribute('embedded')) {
      this.dispatchEvent(new CustomEvent<RegisterSignalSenderDetail>('RegisterSignalSender', {
        bubbles: true,
        composed: true,
        detail: {
          sheetItemId: this.getAttribute('sheet-item-id') ?? '',
          signalId: 'DicePoolRolled',
          connect: (send, disconnect) => {
            this.sendSignal = send;
            this.disconnectSignal = disconnect;
          },
        },
      }));
      this.dispatchEvent(new CustomEvent<RegisterSignalSenderDetail>('RegisterSignalSender', {
        bubbles: true,
        composed: true,
        detail: {
          sheetItemId: this.getAttribute('sheet-item-id') ?? '',
          signalId: 'DicePoolChanged',
          connect: (send, disconnect) => {
            this.sendChangedSignal = send;
            this.disconnectChangedSignal = disconnect;
          },
        },
      }));
      this.dispatchEvent(new CustomEvent<RegisterDatastoreDetail>('RegisterDatastore', {
        bubbles: true,
        composed: true,
        detail: {
          sheetItemId: this.getAttribute('sheet-item-id') ?? '',
          serializeData: () => this.serializePoolData(),
          loadFromSerializedData: (data) => { this.loadPoolData(data); },
          disconnect: () => {},
        },
      }));
    }
  }

  private wireEvents(): void {
    const shadow = this.shadowRoot!;
    const notationInput = shadow.querySelector<HTMLInputElement>('.notation-input')!;
    const invalidMsg = shadow.querySelector<HTMLElement>('.invalid-msg')!;

    shadow.querySelector('.view-controls')!.addEventListener('click', (e) => {
      const target = e.target as Element;
      if (target.closest('.roll-btn')) {
        this.handleRoll();
      } else if (target.closest('.edit-btn')) {
        this._editMode = true;
        this.rollResults = [];
        this.updateView();
      }
    });

    shadow.querySelector('.edit-controls')!.addEventListener('click', (e) => {
      if ((e.target as Element).closest('.done-btn')) {
        this._editMode = false;
        this.rollResults = [];
        this.updateView();
      }
    });

    notationInput.addEventListener('input', () => {
      const parsed = parseDiceNotation(notationInput.value);
      if (parsed !== null) {
        notationInput.classList.remove('invalid');
        invalidMsg.hidden = true;
        this.dice = parsed;
        this.refreshPool();
        this.notifyDiceChanged();
      } else {
        notationInput.classList.add('invalid');
        invalidMsg.hidden = false;
      }
    });

    shadow.querySelector('p.pool')!.addEventListener('click', (e) => {
      if (!this._editMode) return;
      const el = (e.target as Element).closest('.removable');
      if (!el) return;
      const idx = parseInt(el.getAttribute('data-index')!, 10);
      this.dice = this.dice.filter((_, i) => i !== idx);
      notationInput.value = formatDiceNotation(this.dice);
      notationInput.classList.remove('invalid');
      invalidMsg.hidden = true;
      this.refreshPool();
      this.notifyDiceChanged();
    });

    shadow.querySelector('.palette')!.addEventListener('click', (e) => {
      const btn = (e.target as Element).closest('.palette-btn');
      if (!btn) return;
      const sides = parseInt(btn.getAttribute('data-sides')!, 10) as DieSides;
      this.dice = [...this.dice, sides];
      notationInput.value = formatDiceNotation(this.dice);
      this.refreshPool();
      this.notifyDiceChanged();
    });
  }

  private updateView(): void {
    const shadow = this.shadowRoot!;
    const { dice, _editMode: editMode } = this;

    const viewControls = shadow.querySelector<HTMLElement>('.view-controls')!;
    const editControls = shadow.querySelector<HTMLElement>('.edit-controls')!;
    viewControls.style.display = editMode ? 'none' : '';
    editControls.classList.toggle('active', editMode);

    const rollBtn = shadow.querySelector<HTMLButtonElement>('.roll-btn');
    if (rollBtn) rollBtn.disabled = dice.length === 0;

    const notationInput = shadow.querySelector<HTMLInputElement>('.notation-input')!;
    notationInput.value = formatDiceNotation(dice);

    const palette = shadow.querySelector<HTMLElement>('.palette')!;
    if (editMode && palette.children.length === 0) {
      palette.innerHTML = POLYHEDRAL_DICE.map(paletteDieHtml).join('');
    }
    palette.hidden = !editMode;

    this.refreshPool();
  }

  // Public API for embedded use (e.g. inside hex-flower).
  roll(): number[] {
    const rolled = this.dice.map(sides => Math.floor(Math.random() * sides) + 1);
    this.rollResults = rolled;
    this.refreshPool();
    return rolled;
  }

  getState(): string {
    return this.serializePoolData();
  }

  loadState(data: string): void {
    this.loadPoolData(data);
  }

  disconnectedCallback(): void {
    this.disconnectSignal?.();
    this.disconnectChangedSignal?.();
  }

  attributeChangedCallback(_name: string, _old: string | null, value: string | null): void {
    if (this.shadowRoot === null) return;
    this.dice = parseDiceNotation(value ?? '') ?? [];
    this.updateView();
    this.notifyDiceChanged();
  }

  private notifyDiceChanged(): void {
    this.dispatchEvent(new CustomEvent('dice-notation-changed', {
      detail: { notation: formatDiceNotation(this.dice) },
    }));
    this.sendChangedSignal?.(JSON.stringify({ notation: formatDiceNotation(this.dice), dice: [...this.dice] }));
  }


  private serializePoolData(): string {
    return JSON.stringify({ dice: this.dice, rollResults: this.rollResults });
  }

  private loadPoolData(data: string): void {
    const state = JSON.parse(data) as { dice: DieSides[]; rollResults: number[] };
    this.dice = state.dice;
    this.rollResults = state.rollResults;
    this._editMode = false;
    this.updateView();
    this.notifyDiceChanged();
  }

  private handleRoll(): void {
    const rolled = this.dice.map(sides => Math.floor(Math.random() * sides) + 1);
    this.rollResults = rolled;
    this.refreshPool();
    this.sendSignal?.(JSON.stringify({
      notation: formatDiceNotation(this.dice),
      results: this.dice.map((sides, i) => [sides, rolled[i]!]),
    }));
  }

  private refreshPool(): void {
    const shadow = this.shadowRoot;
    if (shadow === null) return;
    const poolEl = shadow.querySelector('p.pool');
    if (!poolEl) return;
    poolEl.innerHTML = this.dice.length > 0
      ? this.dice.map((s, i) => poolDieHtml(s, i, this._editMode, this.rollResults[i] ?? null)).join('')
      : '<span class="empty">No dice in pool</span>';
  }
}

customElements.define('dice-pool', DicePool);
