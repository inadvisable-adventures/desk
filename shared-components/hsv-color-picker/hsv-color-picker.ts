// A dependency-free HSV color wheel + brightness bar + hex field, as a
// standalone custom element. Extracted and generalized from a real,
// already-debugged implementation (necro-4x's TerrainColorInitializer)
// -- see this directory's own README.md for how to use it, and for
// what's specifically non-obvious about the math/pointer handling
// below.

interface Rgb {
  r: number;
  g: number;
  b: number;
}

interface Hsv {
  h: number;
  s: number;
  v: number;
}

const DEFAULT_COLOR = "#888888";

function clamp255(n: number): number {
  return Math.max(0, Math.min(255, Math.round(n)));
}

function clampPct(n: number): number {
  return Math.max(0, Math.min(100, n));
}

function toHex2(n: number): string {
  return clamp255(n).toString(16).padStart(2, "0");
}

function rgbToHex(r: number, g: number, b: number): string {
  return `#${toHex2(r)}${toHex2(g)}${toHex2(b)}`;
}

function hexToRgb(hex: string): Rgb | null {
  const trimmed = hex.trim();
  const long = /^#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/.exec(trimmed);
  if (long) {
    return { r: parseInt(long[1], 16), g: parseInt(long[2], 16), b: parseInt(long[3], 16) };
  }
  const short = /^#([0-9a-fA-F])([0-9a-fA-F])([0-9a-fA-F])$/.exec(trimmed);
  if (short) {
    return {
      r: parseInt(short[1] + short[1], 16),
      g: parseInt(short[2] + short[2], 16),
      b: parseInt(short[3] + short[3], 16),
    };
  }
  return null;
}

// h in [0, 360), s/v in [0, 100].
function hsvToRgb(h: number, s: number, v: number): Rgb {
  const hh = ((h % 360) + 360) % 360;
  const ss = clampPct(s) / 100;
  const vv = clampPct(v) / 100;
  const c = vv * ss;
  const x = c * (1 - Math.abs(((hh / 60) % 2) - 1));
  const m = vv - c;
  let rp = 0;
  let gp = 0;
  let bp = 0;
  if (hh < 60) {
    rp = c;
    gp = x;
  } else if (hh < 120) {
    rp = x;
    gp = c;
  } else if (hh < 180) {
    gp = c;
    bp = x;
  } else if (hh < 240) {
    gp = x;
    bp = c;
  } else if (hh < 300) {
    rp = x;
    bp = c;
  } else {
    rp = c;
    bp = x;
  }
  return { r: clamp255((rp + m) * 255), g: clamp255((gp + m) * 255), b: clamp255((bp + m) * 255) };
}

function rgbToHsv(r: number, g: number, b: number): Hsv {
  const rf = r / 255;
  const gf = g / 255;
  const bf = b / 255;
  const max = Math.max(rf, gf, bf);
  const min = Math.min(rf, gf, bf);
  const delta = max - min;
  let h = 0;
  if (delta !== 0) {
    if (max === rf) h = 60 * (((gf - bf) / delta) % 6);
    else if (max === gf) h = 60 * ((bf - rf) / delta + 2);
    else h = 60 * ((rf - gf) / delta + 4);
  }
  if (h < 0) h += 360;
  const s = max === 0 ? 0 : (delta / max) * 100;
  const v = max * 100;
  return { h, s, v };
}

class HsvColorPickerElement extends HTMLElement {
  // Genuinely hue/sat/val, not just the derived hex string -- hue has
  // no defined value at zero saturation, so re-deriving HSV from a
  // stored hex on every read would make the wheel's cursor jump to an
  // arbitrary angle any time a grayscale color came up, rather than
  // staying where the user last left it.
  private hue = 0;
  private sat = 0;
  private val = 100;
  private currentColor = DEFAULT_COLOR;

  private wheelEl: HTMLElement | null = null;
  private wheelCursorEl: HTMLElement | null = null;
  private brightnessSliderEl: HTMLElement | null = null;
  private brightnessTrackEl: HTMLElement | null = null;
  private brightnessHandleEl: HTMLElement | null = null;
  private hexInput: HTMLInputElement | null = null;

  connectedCallback(): void {
    const template = document.getElementById("hsv-color-picker-template");
    if (!(template instanceof HTMLTemplateElement)) {
      throw new Error(
        "hsv-color-picker-template not found -- paste template.html's <template> block into this document"
      );
    }
    const shadow = this.attachShadow({ mode: "open" });
    shadow.appendChild(template.content.cloneNode(true));

    const wheelEl = shadow.getElementById("wheel");
    const wheelCursorEl = shadow.getElementById("wheel-cursor");
    const brightnessSliderEl = shadow.getElementById("brightness-slider");
    const brightnessTrackEl = shadow.getElementById("brightness-track");
    const brightnessHandleEl = shadow.getElementById("brightness-handle");
    const hexInput = shadow.getElementById("hex-input");
    if (
      !wheelEl ||
      !wheelCursorEl ||
      !brightnessSliderEl ||
      !brightnessTrackEl ||
      !brightnessHandleEl ||
      !(hexInput instanceof HTMLInputElement)
    ) {
      throw new Error("hsv-color-picker: a required control is missing from its template");
    }
    this.wheelEl = wheelEl;
    this.wheelCursorEl = wheelCursorEl;
    this.brightnessSliderEl = brightnessSliderEl;
    this.brightnessTrackEl = brightnessTrackEl;
    this.brightnessHandleEl = brightnessHandleEl;
    this.hexInput = hexInput;

    this.bindWheel();
    this.bindBrightnessSlider();
    this.bindHexInput();

    const initialAttr = this.getAttribute("value");
    const initial = initialAttr && hexToRgb(initialAttr) ? initialAttr : DEFAULT_COLOR;
    this.applyHexColor(initial, false);
  }

  get value(): string {
    return this.currentColor;
  }

  // Matches a native <input>: setting .value in JS never fires
  // input/change -- only a real user interaction (drag/type) does, via
  // the emit=true paths below.
  set value(hex: string) {
    this.applyHexColor(hex, false);
  }

  // A drag session on the wheel/brightness bar: capture the pointer so
  // movement keeps being reported even once it leaves the element's own
  // bounds, and track until pointerup/pointercancel.
  private bindDrag(target: HTMLElement, onPointer: (event: PointerEvent) => void): void {
    target.addEventListener("pointerdown", (event) => {
      try {
        target.setPointerCapture(event.pointerId);
      } catch {
        // A pointerId with no matching active pointer (as with a
        // synthetically-dispatched PointerEvent, e.g. in a headless
        // -Chrome test) rejects capture -- harmless here, since
        // applying the value below doesn't depend on it, only
        // continued tracking once the pointer leaves target.
      }
      onPointer(event);
      const onMove = (moveEvent: PointerEvent) => onPointer(moveEvent);
      const onEnd = () => {
        target.removeEventListener("pointermove", onMove);
        target.removeEventListener("pointerup", onEnd);
        target.removeEventListener("pointercancel", onEnd);
      };
      target.addEventListener("pointermove", onMove);
      target.addEventListener("pointerup", onEnd);
      target.addEventListener("pointercancel", onEnd);
    });
  }

  private bindWheel(): void {
    const wheel = this.wheelEl;
    if (!wheel) return;
    this.bindDrag(wheel, (event) => {
      const rect = wheel.getBoundingClientRect();
      const maxR = rect.width / 2;
      const dx = event.clientX - (rect.left + maxR);
      const dy = event.clientY - (rect.top + maxR);
      const r = Math.min(Math.sqrt(dx * dx + dy * dy), maxR);
      // atan2 in screen space (y down) increases clockwise starting at
      // east/3-o'clock; the wheel's conic-gradient starts at north/12-
      // o'clock and also increases clockwise, hence the +90 offset.
      const hue = ((Math.atan2(dy, dx) * 180) / Math.PI + 90 + 360) % 360;
      const sat = maxR === 0 ? 0 : (r / maxR) * 100;
      this.hue = hue;
      this.sat = clampPct(sat);
      this.applyHsv(true);
    });
  }

  private bindBrightnessSlider(): void {
    const slider = this.brightnessSliderEl;
    if (!slider) return;
    this.bindDrag(slider, (event) => {
      const rect = slider.getBoundingClientRect();
      const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
      const val = rect.height === 0 ? 100 : 100 - (y / rect.height) * 100;
      this.val = clampPct(val);
      this.applyHsv(true);
    });
  }

  private bindHexInput(): void {
    this.hexInput?.addEventListener("input", () => {
      const rgb = this.hexInput ? hexToRgb(this.hexInput.value) : null;
      if (!rgb) return;
      this.applyHexColor(rgbToHex(rgb.r, rgb.g, rgb.b), true);
    });
    this.hexInput?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      this.hexInput?.blur();
    });
    this.hexInput?.addEventListener("blur", () => {
      if (this.hexInput) this.hexInput.value = this.currentColor;
    });
  }

  private applyHexColor(hex: string, emit: boolean): void {
    const rgb = hexToRgb(hex) ?? { r: 0, g: 0, b: 0 };
    const hsv = rgbToHsv(rgb.r, rgb.g, rgb.b);
    this.hue = hsv.h;
    this.sat = hsv.s;
    this.val = hsv.v;
    this.applyHsv(emit);
  }

  private applyHsv(emit: boolean): void {
    const rgb = hsvToRgb(this.hue, this.sat, this.val);
    this.currentColor = rgbToHex(rgb.r, rgb.g, rgb.b);
    if (this.hexInput) this.hexInput.value = this.currentColor;
    this.renderWheelCursor();
    this.renderBrightnessSlider();
    if (emit) {
      this.dispatchEvent(
        new CustomEvent("colorchange", { detail: { hex: this.currentColor }, bubbles: true, composed: true })
      );
    }
  }

  private renderWheelCursor(): void {
    const wheel = this.wheelEl;
    const cursor = this.wheelCursorEl;
    if (!wheel || !cursor) return;
    const rect = wheel.getBoundingClientRect();
    const maxR = rect.width / 2;
    const angleRad = ((this.hue - 90) * Math.PI) / 180;
    const r = (this.sat / 100) * maxR;
    cursor.style.left = `${maxR + r * Math.cos(angleRad)}px`;
    cursor.style.top = `${maxR + r * Math.sin(angleRad)}px`;
  }

  private renderBrightnessSlider(): void {
    const track = this.brightnessTrackEl;
    const handle = this.brightnessHandleEl;
    const slider = this.brightnessSliderEl;
    if (!track || !handle || !slider) return;
    const top = hsvToRgb(this.hue, this.sat, 100);
    track.style.background = `linear-gradient(to bottom, ${rgbToHex(top.r, top.g, top.b)}, #000000)`;
    const rect = slider.getBoundingClientRect();
    handle.style.top = `${((100 - this.val) / 100) * rect.height}px`;
  }
}

customElements.define("hsv-color-picker", HsvColorPickerElement);
