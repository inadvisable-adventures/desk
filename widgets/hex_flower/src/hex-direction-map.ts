import type { DieSides } from './dice-utils.js';
import { computeDiceProbabilities } from './dice-utils.js';
import { hexPoints, hexCenter, neighborCoords, pointInPolygon } from './hex-geometry.js';

type Direction = number | 'stay';

export interface DirectionMapElement extends HTMLElement {
  mapping: Record<number, Direction>;
  dice: DieSides[];
  disabled: boolean;
}

const BAR_COLORS = ['#94a3b8', '#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#a855f7'];
const ZONE_LABELS = ['S', 'A', 'B', 'C', 'D', 'E', 'F'];

const HEX_VIS_SIZE = 28;
const HEX_ANGLE = -Math.PI / 6; // pointy-top
const CHIP_W = 14;
const CHIP_H = 9;
const CHIP_GAP_X = 2;
const CHIP_GAP_Y = 2;
const CHIPS_PER_ROW = 3;

interface ZoneInfo {
  cx: number;
  cy: number;
  pts: [number, number][];
}

function hexVerts(cx: number, cy: number, size: number, angleOffset: number): [number, number][] {
  return Array.from({ length: 6 }, (_, k) => {
    const angle = (Math.PI / 3) * k + angleOffset;
    return [cx + size * Math.cos(angle), cy + size * Math.sin(angle)] as [number, number];
  });
}

class HexDirectionMap extends HTMLElement implements DirectionMapElement {
  private _mapping: Record<number, Direction> = {};
  private _dice: DieSides[] = [];
  private _disabled = false;
  private _drag: { result: number } | null = null;
  private _ghostX = 0;
  private _ghostY = 0;

  static get observedAttributes(): string[] {
    return ['min', 'max'];
  }

  get mapping(): Record<number, Direction> {
    return { ...this._mapping };
  }

  set mapping(val: Record<number, Direction>) {
    this._mapping = { ...val };
    if (this.shadowRoot !== null) this.render();
  }

  set dice(val: DieSides[]) {
    this._dice = [...val];
    if (this.shadowRoot !== null) this.render();
  }

  set disabled(val: boolean) {
    this._disabled = val;
    if (this.shadowRoot !== null) this.render();
  }

  connectedCallback(): void {
    if (this.shadowRoot !== null) return;
    const shadow = this.attachShadow({ mode: 'open' });
    const tpl = document.getElementById('hex-direction-map') as HTMLTemplateElement;
    shadow.appendChild(tpl.content.cloneNode(true));
    this.initMapping();
    this.render();
  }

  attributeChangedCallback(): void {
    if (this.shadowRoot === null) return;
    this.initMapping();
    this.render();
  }

  private get min(): number { return parseInt(this.getAttribute('min') ?? '2', 10); }
  private get max(): number { return parseInt(this.getAttribute('max') ?? '12', 10); }

  private initMapping(): void {
    const updated: Record<number, Direction> = {};
    for (let i = this.min; i <= this.max; i++) {
      updated[i] = this._mapping[i] ?? 'stay';
    }
    this._mapping = updated;
  }

  // ── Zone geometry ────────────────────────────────────────────────────────

  // Zones: index 0 = Stay (center), indices 1-6 = directions 0-5.
  private buildZones(): ZoneInfo[] {
    const raw: { cx: number; cy: number }[] = [];
    raw.push(hexCenter(0, 0, 0, 'pointy', HEX_VIS_SIZE, 0));
    for (let d = 0; d < 6; d++) {
      const nb = neighborCoords(0, 0, 0, d, 'pointy');
      raw.push(hexCenter(nb.na, nb.nr, nb.nc, 'pointy', HEX_VIS_SIZE, 0));
    }

    const margin = HEX_VIS_SIZE + 4;
    const minX = Math.min(...raw.map(c => c.cx));
    const minY = Math.min(...raw.map(c => c.cy));
    const ox = -minX + margin;
    const oy = -minY + margin;

    return raw.map(r => {
      const cx = r.cx + ox;
      const cy = r.cy + oy;
      return { cx, cy, pts: hexVerts(cx, cy, HEX_VIS_SIZE, HEX_ANGLE) };
    });
  }

  // ── Hex visual SVG ───────────────────────────────────────────────────────

  private buildHexVisual(): string {
    const zones = this.buildZones();
    const margin = HEX_VIS_SIZE + 4;
    const svgW = Math.ceil(Math.max(...zones.map(z => z.cx)) + margin);
    const svgH = Math.ceil(Math.max(...zones.map(z => z.cy)) + margin);

    const probs = this._dice.length > 0 ? computeDiceProbabilities(this._dice) : null;
    const dirProbs: Record<string, number> = { stay: 0, '0': 0, '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 };
    if (probs !== null) {
      for (const [roll, prob] of probs) {
        const dir = this._mapping[roll] ?? 'stay';
        const key = dir === 'stay' ? 'stay' : String(dir);
        dirProbs[key] = (dirProbs[key] ?? 0) + prob;
      }
    }

    const innerR = HEX_VIS_SIZE * Math.sqrt(3) / 2;
    const maxBarLen = HEX_VIS_SIZE * Math.sqrt(3);
    const barHalfW = HEX_VIS_SIZE * 0.33;
    const center = zones[0]!;

    // Layer 1: probability bars (behind everything, 50% transparent)
    const bars: string[] = [];
    if (probs !== null) {
      for (let d = 0; d < 6; d++) {
        const zone = zones[d + 1]!;
        const prob = dirProbs[String(d)] ?? 0;
        if (prob <= 0) continue;
        const dx = zone.cx - center.cx;
        const dy = zone.cy - center.cy;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const ux = dx / dist, uy = dy / dist;
        const px = -uy, py = ux; // perpendicular
        const emx = center.cx + ux * innerR;
        const emy = center.cy + uy * innerR;
        const barLen = prob * maxBarLen;
        const p1x = emx - px * barHalfW, p1y = emy - py * barHalfW;
        const p2x = emx + px * barHalfW, p2y = emy + py * barHalfW;
        const p3x = p2x + ux * barLen,    p3y = p2y + uy * barLen;
        const p4x = p1x + ux * barLen,    p4y = p1y + uy * barLen;
        bars.push(
          `<polygon points="${p1x.toFixed(1)},${p1y.toFixed(1)} ${p2x.toFixed(1)},${p2y.toFixed(1)} ${p3x.toFixed(1)},${p3y.toFixed(1)} ${p4x.toFixed(1)},${p4y.toFixed(1)}" fill="${BAR_COLORS[d + 1]}" opacity="0.5"/>`
        );
      }

      // Stay progress bar inside center hex
      const stayProb = dirProbs['stay'] ?? 0;
      const trackW = HEX_VIS_SIZE * 1.2;
      const fillW = stayProb * trackW;
      const barH = 4;
      const barX = center.cx - trackW / 2;
      const barY = center.cy - 2;
      bars.push(`<rect x="${barX.toFixed(1)}" y="${barY.toFixed(1)}" width="${trackW.toFixed(1)}" height="${barH}" fill="#e2e8f0" rx="2" opacity="0.7"/>`);
      if (fillW > 0.5) {
        bars.push(`<rect x="${barX.toFixed(1)}" y="${barY.toFixed(1)}" width="${fillW.toFixed(1)}" height="${barH}" fill="${BAR_COLORS[0]}" rx="2" opacity="0.7"/>`);
      }
    }

    // Layer 2: hex zone polygons (light fill + stroke + direction label)
    const hexPolys: string[] = [];
    for (let i = 0; i < 7; i++) {
      const z = zones[i]!;
      const color = BAR_COLORS[i]!;
      const ptsStr = hexPoints(z.cx, z.cy, HEX_VIS_SIZE, HEX_ANGLE);
      const label = ZONE_LABELS[i]!;
      const labelY = (i === 0 && probs !== null) ? z.cy - 12 : z.cy - 8;
      hexPolys.push(
        `<polygon points="${ptsStr}" fill="${color}" fill-opacity="0.12" stroke="${color}" stroke-width="1.5" pointer-events="none"/>` +
        `<text x="${z.cx}" y="${labelY}" class="zone-lbl" fill="${color}">${label}</text>`
      );
    }

    // Layer 3: result token chips
    const zoneResults: Record<string, number[]> = { stay: [] };
    for (let d = 0; d < 6; d++) zoneResults[String(d)] = [];
    for (let roll = this.min; roll <= this.max; roll++) {
      const dir = this._mapping[roll] ?? 'stay';
      const key = dir === 'stay' ? 'stay' : String(dir);
      (zoneResults[key] ??= []).push(roll);
    }

    const chips: string[] = [];
    for (let i = 0; i < 7; i++) {
      const z = zones[i]!;
      const color = BAR_COLORS[i]!;
      const dirKey = i === 0 ? 'stay' : String(i - 1);
      const results = zoneResults[dirKey] ?? [];
      // Stay zone with probs: 1 row only (progress bar takes vertical space)
      const maxVisible = (i === 0 && probs !== null) ? 3 : 6;
      const hasOverflow = results.length > maxVisible;
      const shown = hasOverflow ? results.slice(0, maxVisible - 1) : results;
      const overflowCount = results.length - shown.length;
      const items: Array<number | null> = [...shown, ...(hasOverflow ? [null] : [])];

      const chipsStartY = (i === 0 && probs !== null) ? z.cy + 8 : z.cy + 2;
      const rowW = CHIPS_PER_ROW * CHIP_W + (CHIPS_PER_ROW - 1) * CHIP_GAP_X;
      const rowStartX = z.cx - rowW / 2 + CHIP_W / 2;

      items.forEach((item, idx) => {
        const col = idx % CHIPS_PER_ROW;
        const row = Math.floor(idx / CHIPS_PER_ROW);
        const chipCx = rowStartX + col * (CHIP_W + CHIP_GAP_X);
        const chipCy = chipsStartY + row * (CHIP_H + CHIP_GAP_Y) + CHIP_H / 2;
        const chipX = (chipCx - CHIP_W / 2).toFixed(1);
        const chipY = (chipCy - CHIP_H / 2).toFixed(1);

        if (item === null) {
          chips.push(
            `<g pointer-events="none">` +
            `<rect x="${chipX}" y="${chipY}" width="${CHIP_W}" height="${CHIP_H}" rx="2" fill="#94a3b8"/>` +
            `<text x="${chipCx.toFixed(1)}" y="${chipCy.toFixed(1)}" class="chip-lbl">+${overflowCount}</text>` +
            `</g>`
          );
        } else {
          chips.push(
            `<g data-result="${item}" class="chip-draggable">` +
            `<rect x="${chipX}" y="${chipY}" width="${CHIP_W}" height="${CHIP_H}" rx="2" fill="${color}"/>` +
            `<text x="${chipCx.toFixed(1)}" y="${chipCy.toFixed(1)}" class="chip-lbl">${item}</text>` +
            `</g>`
          );
        }
      });
    }

    return `
      <svg class="hex-vis" width="${svgW}" height="${svgH}" xmlns="http://www.w3.org/2000/svg">
        <g class="bars">${bars.join('')}</g>
        <g class="hex-fills">${hexPolys.join('')}</g>
        <g class="${this._disabled ? 'chips chips-disabled' : 'chips'}">${chips.join('')}</g>
      </svg>`;
  }

  // ── Dropdown list ────────────────────────────────────────────────────────

  private buildRows(): string {
    const rows: string[] = [];
    for (let i = this.min; i <= this.max; i++) {
      const cur = this._mapping[i] ?? 'stay';
      const opts = [
        `<option value="stay"${cur === 'stay' ? ' selected' : ''}>Stay</option>`,
        ...Array.from({ length: 6 }, (_, d) =>
          `<option value="${d}"${cur === d ? ' selected' : ''}>${'ABCDEF'[d]}</option>`
        ),
      ].join('');
      rows.push(
        `<tr>` +
        `<td class="result-cell">${i}</td>` +
        `<td><select class="dir-select" data-result="${i}"${this._disabled ? ' disabled' : ''}>${opts}</select></td>` +
        `</tr>`
      );
    }
    return rows.join('');
  }

  // ── Render ───────────────────────────────────────────────────────────────

  private render(): void {
    const shadow = this.shadowRoot;
    if (shadow === null) return;
    const { min, max } = this;
    const rows = this.buildRows();
    const emptyMsg = min > max ? '<p class="empty-msg">Add dice to set up directions.</p>' : '';

    shadow.querySelector('.wrap')!.innerHTML = rows.length > 0
      ? `<div class="table-wrap"><table><tbody>${rows}</tbody></table></div>${this.buildHexVisual()}`
      : `${emptyMsg}${this.buildHexVisual()}`;

    shadow.querySelector('tbody')?.addEventListener('change', (e) => {
      const sel = e.target;
      if (!(sel instanceof HTMLSelectElement)) return;
      const result = parseInt(sel.getAttribute('data-result')!, 10);
      const val = sel.value;
      this._mapping[result] = val === 'stay' ? 'stay' : parseInt(val, 10);
      this.render();
      this.dispatchEvent(new CustomEvent('mapping-changed', {
        detail: { mapping: { ...this._mapping } },
      }));
    });

    this.wireHexDrag();
  }

  // ── Drag-and-drop ────────────────────────────────────────────────────────

  private toSvgPt(svg: SVGSVGElement, clientX: number, clientY: number): { x: number; y: number } {
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const ctm = svg.getScreenCTM();
    if (ctm === null) return { x: clientX, y: clientY };
    const t = pt.matrixTransform(ctm.inverse());
    return { x: t.x, y: t.y };
  }

  private appendGhost(svg: SVGSVGElement, result: number, x: number, y: number): void {
    const dir = this._mapping[result] ?? 'stay';
    const zoneIdx = dir === 'stay' ? 0 : (dir as number) + 1;
    const color = BAR_COLORS[zoneIdx]!;

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.classList.add('drag-ghost');
    g.setAttribute('transform', `translate(${(x - CHIP_W / 2).toFixed(1)},${(y - CHIP_H / 2).toFixed(1)})`);
    g.setAttribute('opacity', '0.75');
    g.setAttribute('pointer-events', 'none');

    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('width', String(CHIP_W));
    rect.setAttribute('height', String(CHIP_H));
    rect.setAttribute('rx', '2');
    rect.setAttribute('fill', color);

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', String(CHIP_W / 2));
    text.setAttribute('y', String(CHIP_H / 2));
    text.setAttribute('class', 'chip-lbl');
    text.textContent = String(result);

    g.appendChild(rect);
    g.appendChild(text);
    svg.appendChild(g);
  }

  private wireHexDrag(): void {
    if (this._disabled) return;
    const svg = this.shadowRoot?.querySelector<SVGSVGElement>('.hex-vis');
    if (!svg) return;

    svg.addEventListener('pointerdown', (e) => {
      const chipG = (e.target as Element).closest<SVGGElement>('[data-result]');
      if (!chipG) return;
      const result = parseInt(chipG.getAttribute('data-result')!, 10);
      if (isNaN(result)) return;
      e.preventDefault();
      svg.setPointerCapture(e.pointerId);
      const { x, y } = this.toSvgPt(svg, e.clientX, e.clientY);
      this._drag = { result };
      this._ghostX = x;
      this._ghostY = y;
      chipG.setAttribute('opacity', '0.25');
      this.appendGhost(svg, result, x, y);
    });

    svg.addEventListener('pointermove', (e) => {
      if (this._drag === null) return;
      e.preventDefault();
      const { x, y } = this.toSvgPt(svg, e.clientX, e.clientY);
      this._ghostX = x;
      this._ghostY = y;
      const ghost = svg.querySelector<SVGGElement>('.drag-ghost');
      if (ghost) {
        ghost.setAttribute('transform', `translate(${(x - CHIP_W / 2).toFixed(1)},${(y - CHIP_H / 2).toFixed(1)})`);
      }
    });

    svg.addEventListener('pointerup', (e) => {
      if (this._drag === null) return;
      e.preventDefault();
      const result = this._drag.result;
      this._drag = null;
      const { x, y } = this.toSvgPt(svg, e.clientX, e.clientY);
      const zones = this.buildZones();
      let changed = false;
      for (let i = 0; i < zones.length; i++) {
        if (pointInPolygon(x, y, zones[i]!.pts)) {
          this._mapping[result] = i === 0 ? 'stay' : (i - 1) as number;
          changed = true;
          break;
        }
      }
      this.render();
      if (changed) {
        this.dispatchEvent(new CustomEvent('mapping-changed', {
          detail: { mapping: { ...this._mapping } },
        }));
      }
    });

    svg.addEventListener('pointercancel', () => {
      this._drag = null;
      this.render();
    });
  }
}

customElements.define('hex-direction-map', HexDirectionMap);
