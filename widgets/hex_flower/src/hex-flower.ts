import type { RegisterSignalSenderDetail, RegisterDatastoreDetail } from './signal.types.js';
import {
  type Orientation,
  hexPoints,
  hexCenter,
  neighborCoords,
} from './hex-geometry.js';
import type { DieSides } from './dice-utils.js';

// ── Types ─────────────────────────────────────────────────────────────────

type BoundaryRule = 'bounce' | 'wrap' | 'starting-bounce';
type Direction = number | 'stay';

interface HexFlowerCell {
  a: number;
  r: number;
  c: number;
  tags: string[];
}

interface HexFlowerState {
  orientation: Orientation;
  cells: { a: number; r: number; c: number; tags: string[] }[];
  startingCoords: string;
  currentCoords: string;
  boundaryRule: BoundaryRule;
  directionMap: Record<number, Direction>;
  dicePoolState: string;
  stepCount: number;
  editable: boolean;
  mode?: 'edit' | 'run'; // legacy field for backwards compat
}

// Duck-typed interfaces for embedded custom elements.
interface DicePoolEl extends HTMLElement {
  roll(): number[];
  getState(): string;
  loadState(data: string): void;
  editMode: boolean;
}

interface DirectionMapEl extends HTMLElement {
  mapping: Record<number, Direction>;
  dice: DieSides[];
  disabled: boolean;
}

// ── Constants ─────────────────────────────────────────────────────────────

const SIZE = 30;
const MARGIN = 40;

// ── Helpers ───────────────────────────────────────────────────────────────

function coordKey(a: number, r: number, c: number): string {
  return `${a},${r},${c}`;
}

function parseCoords(key: string): [number, number, number] {
  const p = key.split(',').map(Number);
  return [p[0]!, p[1]!, p[2]!];
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── SVG builders ──────────────────────────────────────────────────────────

function hexGroupSvg(
  a: number, r: number, c: number,
  cx: number, cy: number,
  tags: string[],
  isStarting: boolean,
  isCurrent: boolean,
  isSelected: boolean,
  isGhost: boolean,
  angleOffset: number,
): string {
  const pts = hexPoints(cx, cy, SIZE, angleOffset);

  let fill: string;
  if (isGhost) fill = 'rgba(203,213,225,0.25)';
  else if (isStarting) fill = '#fef9c3';
  else fill = '#ffffff';

  const strokeColor = isSelected ? '#6366f1' : (isGhost ? '#94a3b8' : '#334155');
  const strokeWidth = isSelected ? '3' : (isGhost ? '1' : '1.5');
  const dashAttr = isGhost ? ' stroke-dasharray="4 3"' : '';

  const ring = isCurrent
    ? `<polygon points="${hexPoints(cx, cy, SIZE - 3, angleOffset)}" fill="none" stroke="#6366f1" stroke-width="3"/>`
    : '';

  // Tags: up to 3 lines, truncate rest with ellipsis
  const displayTags = tags.length > 3 ? [...tags.slice(0, 2), '…'] : tags;
  const lineH = 11;
  const startY = cy - (displayTags.length - 1) * lineH / 2;
  const tagsSvg = displayTags.map((tag, i) =>
    `<text x="${cx.toFixed(1)}" y="${(startY + i * lineH).toFixed(1)}" class="tag-label">${escapeXml(tag)}</text>`
  ).join('');

  const type = isGhost ? 'ghost' : 'hex';
  return (
    `<g data-type="${type}" data-a="${a}" data-r="${r}" data-c="${c}" style="cursor:pointer">` +
    `<polygon points="${pts}" fill="${fill}" stroke="${strokeColor}" stroke-width="${strokeWidth}"${dashAttr}/>` +
    ring +
    tagsSvg +
    `</g>`
  );
}

function buildSvgContent(
  cells: Map<string, HexFlowerCell>,
  startingCoords: string,
  currentCoords: string,
  selectedCoords: string | null,
  mode: 'edit' | 'run',
  orientation: Orientation,
): { svgHtml: string; svgWidth: number; svgHeight: number } {
  const angleOffset = orientation === 'flat' ? 0 : -Math.PI / 6;

  // Collect ghost coords in edit mode
  const realKeys = new Set(cells.keys());
  const ghostKeys = new Set<string>();
  if (mode === 'edit') {
    for (const key of realKeys) {
      const [a, r, c] = parseCoords(key);
      for (let d = 0; d < 6; d++) {
        const nb = neighborCoords(a, r, c, d, orientation);
        const nbKey = coordKey(nb.na, nb.nr, nb.nc);
        if (!realKeys.has(nbKey)) ghostKeys.add(nbKey);
      }
    }
  }

  // Compute centers at padding=0 then find bounding box
  const allKeys = [...realKeys, ...ghostKeys];
  if (allKeys.length === 0) {
    return { svgHtml: '', svgWidth: 100, svgHeight: 100 };
  }

  const centers = new Map<string, { cx: number; cy: number }>();
  for (const key of allKeys) {
    const [a, r, c] = parseCoords(key);
    centers.set(key, hexCenter(a, r, c, orientation, SIZE, 0));
  }

  const cxVals = [...centers.values()].map(c => c.cx);
  const cyVals = [...centers.values()].map(c => c.cy);
  const minCX = Math.min(...cxVals);
  const maxCX = Math.max(...cxVals);
  const minCY = Math.min(...cyVals);
  const maxCY = Math.max(...cyVals);

  const offsetX = MARGIN + SIZE - minCX;
  const offsetY = MARGIN + SIZE - minCY;
  const svgWidth = Math.ceil(maxCX - minCX + 2 * (SIZE + MARGIN));
  const svgHeight = Math.ceil(maxCY - minCY + 2 * (SIZE + MARGIN));

  const groups: string[] = [];

  for (const key of realKeys) {
    const cell = cells.get(key)!;
    const { cx: rawCX, cy: rawCY } = centers.get(key)!;
    groups.push(hexGroupSvg(
      cell.a, cell.r, cell.c,
      rawCX + offsetX, rawCY + offsetY,
      cell.tags,
      key === startingCoords,
      key === currentCoords,        // always show current position ring
      key === selectedCoords && mode === 'edit',
      false,
      angleOffset,
    ));
  }

  for (const key of ghostKeys) {
    const [a, r, c] = parseCoords(key);
    const { cx: rawCX, cy: rawCY } = centers.get(key)!;
    groups.push(hexGroupSvg(
      a, r, c,
      rawCX + offsetX, rawCY + offsetY,
      [], false, false, false, true, angleOffset,
    ));
  }

  const svgHtml =
    `<svg class="hex-svg" width="${svgWidth}" height="${svgHeight}" xmlns="http://www.w3.org/2000/svg">` +
    `<style>` +
    `.tag-label{font-size:8px;font-family:sans-serif;fill:#1e293b;text-anchor:middle;dominant-baseline:middle;pointer-events:none;user-select:none}` +
    `</style>` +
    groups.join('') +
    `</svg>`;

  return { svgHtml, svgWidth, svgHeight };
}

// ── Component ─────────────────────────────────────────────────────────────

class HexFlower extends HTMLElement {
  private cells = new Map<string, HexFlowerCell>();
  private orientation: Orientation = 'pointy';
  private startingCoords = '0,0,0';
  private currentCoords = '0,0,0';
  private editable = true;
  private selectedCoords: string | null = null;
  private boundaryRule: BoundaryRule = 'bounce';
  private directionMap: Record<number, Direction> = {};
  private stepCount = 5;
  private running = false;
  private sendSignal: ((msg: string) => void) | null = null;
  private disconnectSignal: (() => void) | null = null;
  private savedDiceState: string = JSON.stringify({ dice: [], rollResults: [] });

  connectedCallback(): void {
    if (this.shadowRoot !== null) return;
    this.attachShadow({ mode: 'open' });
    if (this.cells.size === 0) {
      this.cells.set('0,0,0', { a: 0, r: 0, c: 0, tags: [] });
    }
    this.fullRender();

    this.dispatchEvent(new CustomEvent<RegisterSignalSenderDetail>('RegisterSignalSender', {
      bubbles: true,
      composed: true,
      detail: {
        sheetItemId: this.getAttribute('sheet-item-id') ?? '',
        signalId: 'HexFlowerMove',
        connect: (send, disconnect) => {
          this.sendSignal = send;
          this.disconnectSignal = disconnect;
        },
      },
    }));

    this.dispatchEvent(new CustomEvent<RegisterDatastoreDetail>('RegisterDatastore', {
      bubbles: true,
      composed: true,
      detail: {
        sheetItemId: this.getAttribute('sheet-item-id') ?? '',
        serializeData: () => this.serializeData(),
        loadFromSerializedData: (data) => { this.loadData(data); },
        disconnect: () => {},
      },
    }));
  }

  disconnectedCallback(): void {
    this.disconnectSignal?.();
  }

  // ── Serialization ────────────────────────────────────────────────────────

  private serializeData(): string {
    const dicePoolEl = this.shadowRoot?.querySelector('dice-pool') as unknown as DicePoolEl | null;
    const diceState = dicePoolEl ? dicePoolEl.getState() : this.savedDiceState;
    const state: HexFlowerState = {
      orientation: this.orientation,
      cells: [...this.cells.values()],
      startingCoords: this.startingCoords,
      currentCoords: this.currentCoords,
      boundaryRule: this.boundaryRule,
      directionMap: this.directionMap,
      dicePoolState: diceState,
      stepCount: this.stepCount,
      editable: this.editable,
    };
    return JSON.stringify(state);
  }

  private loadData(data: string): void {
    const state = JSON.parse(data) as HexFlowerState;
    this.orientation = state.orientation;
    this.cells = new Map(
      state.cells.map(c => [coordKey(c.a, c.r, c.c), c])
    );
    this.startingCoords = state.startingCoords;
    this.currentCoords = state.currentCoords;
    this.boundaryRule = state.boundaryRule;
    this.directionMap = state.directionMap;
    this.savedDiceState = state.dicePoolState;
    this.stepCount = state.stepCount;
    // Backwards compat: old saves use mode:'edit'|'run' instead of editable
    this.editable = state.editable ?? (state.mode !== 'run');
    this.selectedCoords = null;
    this.fullRender();
  }

  // ── Full render ──────────────────────────────────────────────────────────

  private fullRender(): void {
    const shadow = this.shadowRoot!;

    // Save current state from embedded elements before rebuilding DOM
    const dicePoolEl = shadow.querySelector('dice-pool') as unknown as DicePoolEl | null;
    if (dicePoolEl) this.savedDiceState = dicePoolEl.getState();

    const dirMapEl = shadow.querySelector('hex-direction-map') as unknown as DirectionMapEl | null;
    if (dirMapEl) this.directionMap = dirMapEl.mapping;

    shadow.innerHTML = this.buildFullHtml();
    this.wireEditableToggle();
    this.wireSvgClicks();
    this.wireRunControls();
    this.wireDetailPanelEvents();
    this.restoreRunState();
  }

  // Partial re-render: only replaces SVG and detail panel, preserves controls.
  private partialRender(): void {
    const shadow = this.shadowRoot!;
    const svgWrapper = shadow.querySelector('.svg-wrapper');
    if (!svgWrapper) { this.fullRender(); return; }

    const { svgHtml } = buildSvgContent(
      this.cells, this.startingCoords, this.currentCoords,
      this.selectedCoords, this.editable ? 'edit' : 'run', this.orientation,
    );
    svgWrapper.innerHTML = svgHtml;
    this.wireSvgClicks();

    const detailPanel = shadow.querySelector('.detail-panel');
    if (detailPanel) {
      detailPanel.innerHTML = this.buildDetailPanelHtml();
      this.wireDetailPanelEvents();
    }
  }

  // ── HTML builders ─────────────────────────────────────────────────────────

  private buildFullHtml(): string {
    const { svgHtml } = buildSvgContent(
      this.cells, this.startingCoords, this.currentCoords,
      this.selectedCoords, this.editable ? 'edit' : 'run', this.orientation,
    );

    return `
      <style>${this.buildStyles()}</style>
      <div class="container">
        <div class="header">
          <span class="title">Hex Flower</span>
          <label class="orient-label">
            <input type="radio" name="orient" value="pointy"${this.orientation === 'pointy' ? ' checked' : ''}${!this.editable ? ' disabled' : ''}> Pointy
          </label>
          <label class="orient-label">
            <input type="radio" name="orient" value="flat"${this.orientation === 'flat' ? ' checked' : ''}${!this.editable ? ' disabled' : ''}> Flat
          </label>
          <label class="editable-toggle-label">
            <input type="checkbox" class="editable-check"${this.editable ? ' checked' : ''}> Editable
          </label>
        </div>
        <div class="run-layout">
          <div class="svg-wrapper">${svgHtml}</div>
          ${this.buildControlsPanelHtml()}
        </div>
      </div>
    `;
  }

  private buildDetailPanelHtml(): string {
    if (!this.selectedCoords) {
      return `<p class="hint">Click a hex to edit its tags, or click a ghost (dashed) hex to add it.</p>`;
    }
    const cell = this.cells.get(this.selectedCoords);
    if (!cell) return '';

    const isStarting = this.selectedCoords === this.startingCoords;
    const tagChips = cell.tags.map((tag, i) =>
      `<span class="tag-chip">${escapeXml(tag)}<button class="remove-tag" data-index="${i}">×</button></span>`
    ).join('');

    return `
      <div class="detail-inner">
        <div class="tag-row">
          ${tagChips}
          <input class="tag-input" type="text" placeholder="Add tag…">
          <button class="add-tag-btn">+</button>
        </div>
        <div class="detail-actions">
          <button class="set-starting-btn"${isStarting ? ' disabled' : ''}>${isStarting ? '★ Starting hex' : 'Set as starting hex'}</button>
          <button class="remove-hex-btn">Remove hex</button>
        </div>
      </div>
    `;
  }

  private buildControlsPanelHtml(): string {
    const boundaryOptions = [
      ['bounce', 'Bounce (stay)'],
      ['wrap', 'Wrap (opposite edge)'],
      ['starting-bounce', 'Wrap / bounce on start'],
    ].map(([val, label]) =>
      `<option value="${val}"${this.boundaryRule === val ? ' selected' : ''}>${label}</option>`
    ).join('');

    const detailSection = this.editable
      ? `<div class="detail-panel">${this.buildDetailPanelHtml()}</div>`
      : '';

    return `
      <div class="controls-panel">
        <section class="ctrl-section">
          <div class="ctrl-label">Dice</div>
          <dice-pool embedded></dice-pool>
        </section>
        <section class="ctrl-section">
          <div class="ctrl-label">Direction Map</div>
          <hex-direction-map min="0" max="0"></hex-direction-map>
        </section>
        <section class="ctrl-section">
          <div class="ctrl-label">Boundary Rule</div>
          <select class="boundary-select"${!this.editable ? ' disabled' : ''}>${boundaryOptions}</select>
        </section>
        <section class="ctrl-section step-section">
          <button class="step-btn">Step ×1</button>
          <button class="run-btn">Run ×</button>
          <input class="step-count" type="number" value="${this.stepCount}" min="1" max="999" style="width:52px">
        </section>
        ${detailSection}
      </div>
    `;
  }

  private buildStyles(): string {
    return `
      button { user-select: none; }
      :host { display: block; font-family: sans-serif; }
      .container { border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; display: inline-block; min-width: 200px; }
      .header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
      .title { font-weight: 600; font-size: 14px; color: #1e293b; flex: 1 1 auto; }
      .orient-label { font-size: 12px; color: #475569; cursor: pointer; }
      .editable-toggle-label { font-size: 12px; color: #475569; cursor: pointer; margin-left: auto; }
      .run-layout { display: flex; gap: 16px; align-items: flex-start; flex-wrap: wrap; }
      .svg-wrapper { overflow: auto; max-width: 480px; max-height: 480px; }
      .hex-svg { display: block; }
      .detail-panel { border-top: 1px solid #e2e8f0; padding-top: 8px; margin-top: 4px; min-height: 60px; }
      .hint { font-size: 12px; color: #94a3b8; margin: 0; }
      .detail-inner { display: flex; flex-direction: column; gap: 6px; }
      .tag-row { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
      .tag-chip {
        display: inline-flex; align-items: center; gap: 3px;
        background: #e0e7ff; color: #3730a3;
        border-radius: 99px; padding: 2px 8px; font-size: 12px;
      }
      .remove-tag {
        background: none; border: none; cursor: pointer; padding: 0;
        font-size: 12px; color: #6366f1; line-height: 1;
      }
      .tag-input {
        font-size: 12px; border: 1px solid #cbd5e1; border-radius: 4px;
        padding: 2px 6px; width: 100px;
      }
      .add-tag-btn {
        font-size: 14px; padding: 1px 7px;
        border: 1px solid #94a3b8; border-radius: 4px;
        background: #f8fafc; cursor: pointer;
      }
      .add-tag-btn:hover { background: #e2e8f0; }
      .detail-actions { display: flex; gap: 8px; flex-wrap: wrap; }
      .set-starting-btn, .remove-hex-btn {
        font-size: 12px; padding: 3px 10px;
        border-radius: 4px; cursor: pointer; border: 1px solid;
      }
      .set-starting-btn { border-color: #f59e0b; background: #fffbeb; color: #92400e; }
      .set-starting-btn:disabled { opacity: 0.5; cursor: default; }
      .remove-hex-btn { border-color: #ef4444; background: #fff1f2; color: #b91c1c; }
      .remove-hex-btn:hover { background: #fee2e2; }
      .controls-panel { display: flex; flex-direction: column; gap: 10px; min-width: 240px; }
      .ctrl-section { display: flex; flex-direction: column; gap: 4px; }
      .ctrl-label { font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; }
      .boundary-select { font-size: 12px; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 6px; cursor: pointer; }
      .boundary-select:disabled { opacity: 0.5; cursor: default; }
      .step-section { flex-direction: row; align-items: center; flex-wrap: wrap; gap: 6px; }
      .step-btn, .run-btn {
        font-size: 12px; padding: 4px 10px;
        border: 1px solid #6366f1; border-radius: 4px;
        background: #6366f1; color: white; cursor: pointer;
      }
      .step-btn:hover:not(:disabled), .run-btn:hover:not(:disabled) { background: #4f46e5; }
      .step-btn:disabled, .run-btn:disabled { opacity: 0.4; cursor: default; }
      .step-count { font-size: 12px; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 4px; }
    `;
  }

  // ── Event wiring ──────────────────────────────────────────────────────────

  private wireSvgClicks(): void {
    const svg = this.shadowRoot?.querySelector('.hex-svg');
    if (!svg || !this.editable) return;
    svg.addEventListener('click', (e) => {
      const g = (e.target as Element).closest<SVGGElement>('g[data-type]');
      if (!g) return;
      const type = g.getAttribute('data-type');
      const a = parseInt(g.getAttribute('data-a')!, 10);
      const r = parseInt(g.getAttribute('data-r')!, 10);
      const c = parseInt(g.getAttribute('data-c')!, 10);
      if (type === 'ghost') {
        this.addHex(a, r, c);
      } else {
        const key = coordKey(a, r, c);
        this.selectedCoords = this.selectedCoords === key ? null : key;
        this.partialRender();
      }
    });
  }

  private wireEditableToggle(): void {
    const shadow = this.shadowRoot!;

    shadow.querySelector<HTMLInputElement>('.editable-check')
      ?.addEventListener('change', (e) => {
        this.editable = (e.target as HTMLInputElement).checked;
        if (!this.editable) this.selectedCoords = null;
        this.fullRender();
      });

    shadow.querySelectorAll<HTMLInputElement>('input[name="orient"]').forEach(input => {
      input.addEventListener('change', () => {
        this.orientation = input.value as Orientation;
        this.selectedCoords = null;
        this.fullRender();
      });
    });
  }

  private wireDetailPanelEvents(): void {
    const shadow = this.shadowRoot!;

    shadow.querySelector('.add-tag-btn')?.addEventListener('click', () => {
      const input = shadow.querySelector<HTMLInputElement>('.tag-input');
      if (!input || !this.selectedCoords) return;
      const tag = input.value.trim();
      if (!tag) return;
      const cell = this.cells.get(this.selectedCoords);
      if (cell) { cell.tags = [...cell.tags, tag]; }
      input.value = '';
      this.partialRender();
    });

    shadow.querySelector<HTMLInputElement>('.tag-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        shadow.querySelector<HTMLButtonElement>('.add-tag-btn')?.click();
      }
    });

    shadow.querySelectorAll('.remove-tag').forEach(btn => {
      btn.addEventListener('click', () => {
        if (!this.selectedCoords) return;
        const idx = parseInt((btn as HTMLElement).getAttribute('data-index')!, 10);
        const cell = this.cells.get(this.selectedCoords);
        if (cell) { cell.tags = cell.tags.filter((_, i) => i !== idx); }
        this.partialRender();
      });
    });

    shadow.querySelector('.set-starting-btn')?.addEventListener('click', () => {
      if (!this.selectedCoords) return;
      this.startingCoords = this.selectedCoords;
      this.partialRender();
    });

    shadow.querySelector('.remove-hex-btn')?.addEventListener('click', () => {
      if (!this.selectedCoords) return;
      this.removeHex(this.selectedCoords);
    });
  }

  private wireRunControls(): void {
    const shadow = this.shadowRoot!;

    shadow.querySelector('.boundary-select')?.addEventListener('change', (e) => {
      this.boundaryRule = (e.target as HTMLSelectElement).value as BoundaryRule;
    });

    shadow.querySelector<HTMLInputElement>('.step-count')?.addEventListener('change', (e) => {
      const n = parseInt((e.target as HTMLInputElement).value, 10);
      if (!isNaN(n) && n > 0) this.stepCount = n;
    });

    shadow.querySelector('.step-btn')?.addEventListener('click', () => {
      if (!this.running) this.doStep();
    });

    shadow.querySelector('.run-btn')?.addEventListener('click', () => {
      if (!this.running) this.doRunN(this.stepCount);
    });
  }

  private restoreRunState(): void {
    const shadow = this.shadowRoot!;

    const dicePoolEl = shadow.querySelector('dice-pool') as unknown as DicePoolEl;
    if (dicePoolEl) {
      dicePoolEl.loadState(this.savedDiceState);
      dicePoolEl.editMode = this.editable;
      dicePoolEl.addEventListener('dice-notation-changed', () => this.syncDirectionMapRange());
    }

    const dirMapEl = shadow.querySelector('hex-direction-map') as unknown as DirectionMapEl;
    if (dirMapEl) {
      dirMapEl.disabled = !this.editable;
      dirMapEl.addEventListener('mapping-changed', (e) => {
        this.directionMap = (e as CustomEvent<{ mapping: Record<number, Direction> }>).detail.mapping;
      });
    }

    this.syncDirectionMapRange();
  }

  // ── Hex editing ───────────────────────────────────────────────────────────

  private addHex(a: number, r: number, c: number): void {
    const key = coordKey(a, r, c);
    if (this.cells.has(key)) return;
    this.cells.set(key, { a, r, c, tags: [] });
    this.partialRender();
  }

  private removeHex(key: string): void {
    if (this.cells.size <= 1) return; // keep at least one hex
    this.cells.delete(key);
    if (this.selectedCoords === key) this.selectedCoords = null;
    if (this.startingCoords === key) {
      this.startingCoords = this.cells.keys().next().value ?? '0,0,0';
    }
    if (this.currentCoords === key) {
      this.currentCoords = this.startingCoords;
    }
    this.partialRender();
  }

  // ── Direction map sync ────────────────────────────────────────────────────

  private syncDirectionMapRange(): void {
    const shadow = this.shadowRoot;
    if (shadow === null) return;
    const dicePoolEl = shadow.querySelector('dice-pool') as unknown as DicePoolEl | null;
    const dirMapEl = shadow.querySelector('hex-direction-map') as unknown as DirectionMapEl | null;
    if (!dicePoolEl || !dirMapEl) return;

    const state = JSON.parse(dicePoolEl.getState()) as { dice: DieSides[]; rollResults: number[] };
    const dice = state.dice;

    let min: number, max: number;
    if (dice.length === 0) {
      min = 0; max = 0;
    } else {
      min = dice.length;
      max = dice.reduce((s, d) => s + d, 0);
    }

    // Build display mapping preserving existing entries in new range.
    const displayMapping: Record<number, Direction> = {};
    for (let i = min; i <= max; i++) {
      displayMapping[i] = this.directionMap[i] ?? 'stay';
    }

    dirMapEl.setAttribute('min', String(min));
    dirMapEl.setAttribute('max', String(max));
    dirMapEl.mapping = displayMapping;
    dirMapEl.dice = dice;
    this.directionMap = displayMapping;
  }

  // ── Movement ─────────────────────────────────────────────────────────────

  private doStep(): void {
    const shadow = this.shadowRoot;
    if (shadow === null) return;

    const dicePoolEl = shadow.querySelector('dice-pool') as unknown as DicePoolEl;
    const results = dicePoolEl ? dicePoolEl.roll() : [];
    const total = results.reduce((s, v) => s + v, 0);
    const direction: Direction = this.directionMap[total] ?? 'stay';

    const [a, r, c] = parseCoords(this.currentCoords);
    let nextA = a, nextR = r, nextC = c;
    let bounced = false, wrapped = false;

    if (direction !== 'stay') {
      const d = direction as number;
      const nb = neighborCoords(a, r, c, d, this.orientation);
      const nbKey = coordKey(nb.na, nb.nr, nb.nc);

      if (this.cells.has(nbKey)) {
        nextA = nb.na; nextR = nb.nr; nextC = nb.nc;
      } else {
        const isOnStart = this.currentCoords === this.startingCoords;
        if (this.boundaryRule === 'bounce' || (this.boundaryRule === 'starting-bounce' && isOnStart)) {
          bounced = true;
        } else {
          wrapped = true;
          [nextA, nextR, nextC] = this.computeWrapTarget(a, r, c, d);
        }
      }
    }

    this.currentCoords = coordKey(nextA, nextR, nextC);
    this.partialRender();

    const cell = this.cells.get(this.currentCoords);
    this.sendSignal?.(JSON.stringify({
      diceRolled: results,
      rollTotal: total,
      direction,
      coordinates: this.currentCoords,
      tags: cell?.tags ?? [],
      bounced,
      wrapped,
    }));
  }

  private doRunN(n: number): void {
    if (this.running) return;
    this.running = true;
    this.setStepButtonsDisabled(true);

    const step = (i: number): void => {
      if (i >= n) {
        this.running = false;
        this.setStepButtonsDisabled(false);
        return;
      }
      this.doStep();
      setTimeout(() => { step(i + 1); }, 350);
    };
    step(0);
  }

  private setStepButtonsDisabled(disabled: boolean): void {
    const shadow = this.shadowRoot;
    if (!shadow) return;
    shadow.querySelector<HTMLButtonElement>('.step-btn')?.toggleAttribute('disabled', disabled);
    shadow.querySelector<HTMLButtonElement>('.run-btn')?.toggleAttribute('disabled', disabled);
  }

  // Walk opposite direction until we'd step off the cell set; return last valid position.
  private computeWrapTarget(a: number, r: number, c: number, d: number): [number, number, number] {
    const oppositeDir = (d + 3) % 6;
    let ca = a, cr = r, cc = c;
    for (;;) {
      const nb = neighborCoords(ca, cr, cc, oppositeDir, this.orientation);
      if (!this.cells.has(coordKey(nb.na, nb.nr, nb.nc))) break;
      ca = nb.na; cr = nb.nr; cc = nb.nc;
    }
    return [ca, cr, cc];
  }
}

customElements.define('hex-flower', HexFlower);
