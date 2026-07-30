# hsv-color-picker

A self-contained, dependency-free HSV color wheel + brightness bar +
hex field, packaged as a custom element (`<hsv-color-picker>`). No
build step, no runtime dependencies — just the two files in this
directory.

Extracted and generalized from a real, already-shipped implementation
(`necro-4x`'s `TerrainColorInitializer`), which went through three
design iterations before landing here — a native `<input
type="color">` (rejected: always opens as an undockable OS popup, no
way to keep it docked inline), three plain RGB sliders (functional,
but no visual intuition for the resulting color), then this. See the
"Why not simpler" section below for the non-obvious parts that made
this version worth keeping around instead of re-deriving next time.

## When to use this

Reach for this when a `DefineWidget`/browser-kind widget needs a real
color picker and a bare `<input type="color">` isn't good enough (e.g.
it needs to stay docked inline in the widget's own layout, or you want
a visual hue/saturation/brightness control rather than three abstract
sliders).

## How to use it

Two supported ways — pick whichever fits:

1. **Import it as-is.** Copy this whole `hsv-color-picker/` directory
   into your project (e.g. next to `custom_widget_src/shared/`), then:
   ```ts
   import "../shared-components/hsv-color-picker/hsv-color-picker";
   ```
   (a side-effect import — it registers the `<hsv-color-picker>`
   custom element, nothing to assign).
2. **Copy, paste, and modify.** Copy `hsv-color-picker.ts` and
   `template.html`'s contents directly into your own widget's source
   and change whatever you need (colors, sizing, adding an alpha
   channel, whatever). Nothing about it assumes it'll stay unmodified.

Either way, **`template.html`'s `<template>` block has to be pasted
into your widget's own HTML document** (there's no bundler here to
inline it automatically) — the same "look up a `<template>` by id"
shape every widget authored via "Authoring from real source" (see
`tempui-custom-widgets.md`) already uses for its own markup. Put it
anywhere before the `<hsv-color-picker>` element itself is used.

Then, in markup:

```html
<hsv-color-picker value="#3daee9"></hsv-color-picker>
```

And in code:

```ts
const picker = document.querySelector("hsv-color-picker") as HTMLElement & { value: string };
picker.addEventListener("colorchange", (event) => {
  const hex = (event as CustomEvent<{ hex: string }>).detail.hex;
  // ... do something with hex ...
});

// Read the current color at any time:
console.log(picker.value); // e.g. "#3daee9"

// Set it programmatically (does NOT fire colorchange -- same
// convention as a native <input>'s .value setter):
picker.value = "#ff0000";
```

## API

- `value` (property, get/set): the current color as a `"#rrggbb"` hex
  string. An optional `value="#rrggbb"` HTML attribute seeds the
  initial color once, at connect time.
- `colorchange` (`CustomEvent<{ hex: string }>`, bubbles, composed):
  fired whenever the user actually changes the color — dragging the
  wheel, dragging the brightness bar, or typing into the hex field.
  **Not** fired by setting `.value` in code.

## Why not simpler (the non-obvious parts)

- The wheel is two stacked CSS gradients, no canvas, no per-pixel
  drawing: `conic-gradient(from 0deg, red, yellow, lime, cyan, blue,
  magenta, red)` for hue, plus a `radial-gradient(circle, #fff 0%,
  rgba(255,255,255,0) 100%)` overlay for saturation. This is exact,
  not an approximation — HSV saturation at a given radius is a linear
  mix between white and the pure hue color, and the browser computes
  that exact mix at every point for free via alpha compositing.
- Reading a pointer position back into hue needs a screen-angle-to-CSS
  -angle conversion that's easy to get backwards: `atan2(dy, dx)` in
  screen space (y down) increases clockwise from due east, while
  `conic-gradient(from 0deg, ...)` starts due north and also increases
  clockwise — so it needs exactly a `+90°` offset. Getting this wrong
  doesn't error, it just makes the color under the cursor subtly not
  match the color actually picked.
- Internal state is genuinely `hue`/`sat`/`val`, not just the derived
  hex string — hue has no defined value at zero saturation, so
  re-deriving HSV from a stored hex on every read would make the
  wheel's cursor jump to an arbitrary angle any time a grayscale color
  came up, instead of staying where the user last left it.
- Dragging uses real `pointerdown`/`pointermove`/`pointerup` with
  `setPointerCapture` so movement keeps being tracked even once the
  pointer leaves the wheel/bar's own bounds mid-drag — wrapped in
  `try`/`catch` specifically because a synthetically-dispatched
  `PointerEvent` (as a headless-Chrome test would use) has no real
  "active pointer" for the browser to capture, and capture failing
  shouldn't block the value from applying.
