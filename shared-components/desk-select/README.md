# desk-select

A self-contained, dependency-free replacement for a native `<select>`,
packaged as a custom element (`<desk-select>`). No build step, no
runtime dependencies -- just the two files in this directory.

## When to use this

**Use it instead of a native `<select>` in any `DefineWidget` /
`kind: "html"` widget.** A widget's page is embedded in the zoomable,
pannable Workspace Canvas. A native `<select>` (and the other controls
below) opens its list as a separate OS-level popup, positioned from
screen coordinates that ignore the canvas transform -- so with the
canvas away from identity zoom/pan, the list renders detached from the
control. This is the HTML twin of the `QComboBox` problem
`PaintedComboBox` solves for Python widgets.

`<desk-select>`'s list is ordinary page content (`position: fixed`
inside its own shadow root), so it moves, scales and clips exactly like
the rest of the page.

Other native controls that open an OS-level popup have the same
exposure -- avoid them under the canvas too: `<input type="date">` /
`time` / `month` / `week` / `datetime-local` (calendar popup), `<input
type="color">`, `<input list="...">` (autocomplete list), and the
browser's own context menu. For color, see `../hsv-color-picker/`.

## How to use it

Same two ways as the other components:

1. **Import it as-is.** Copy this directory next to your widget's
   source and `import "../shared-components/desk-select/desk-select";`
   (a side-effect import; registers `<desk-select>`).
2. **Copy, paste, and modify.**

Either way, **paste `template.html`'s `<template>` block into your
widget's own HTML document**, anywhere before the first
`<desk-select>` is created (the element looks up `#desk-select-template`
in its constructor and throws a clear error if it's missing). This
works for a `<desk-select>` inside another component's shadow root too:
the template is looked up in the main document, so one copy serves the
whole page.

Then, in markup -- the same `<option>` children a `<select>` takes:

```html
<desk-select value="minor">
  <option value="major">Major</option>
  <option value="minor">Minor</option>
  <option value="free">Free</option>
</desk-select>
```

And in code:

```ts
const sel = document.querySelector("desk-select") as HTMLElement & { value: string };
sel.addEventListener("change", () => console.log(sel.value));
sel.value = "major"; // programmatic; fires no event, like <select>
```

## What matches `<select>`

- `<option>` children (`value` attribute or, absent that, the text;
  `selected`; `disabled`). Adding/removing/editing options later is
  picked up automatically.
- `value`, `selectedIndex`, `disabled` (property and attribute),
  `options`. Initial selection: `value` attribute, else the `selected`
  option, else the first enabled option. Setting `value` to something
  with no matching option selects nothing (`value` is `""`).
- `input` and `change` events -- `bubbles` and `composed`, fired only on
  a user-driven change, so a listener on `document` or on a shadow
  host's ancestor sees them.
- Keyboard: Arrow keys, Home/End, Enter/Space, Escape, Tab, and
  type-ahead; ARIA `combobox`/`listbox`/`option`.

## Not supported (yet)

`<optgroup>` (its options show as one flat list), `multiple`, `size`,
`name`/form submission, and `<option>` images/rich content. Style it
with the CSS variables `--desk-select-color`, `--desk-select-bg`,
`--desk-select-border`, `--desk-select-list-bg`, `--desk-select-accent`
and `--desk-select-accent-text`, or `::part(button)`.

## Why not simpler

- **`position: fixed`, not `absolute`:** the list is never clipped by an
  `overflow: auto` ancestor (a scrolling tab body, a table cell). The
  catch: an ancestor with a CSS `transform`, `filter` or `contain:
  paint` becomes the containing block for fixed descendants and would
  mis-place it -- don't put `<desk-select>` under one of those.
- **It closes on any scroll** (capturing listener) and on window resize,
  because a fixed list would otherwise stay put while its control
  scrolls away.
- **Outside-click uses `composedPath()`**, not `contains()`, so it's
  correct when the select lives inside a shadow root.
- **The list swallows `pointerdown`** (`preventDefault`) so clicking an
  option doesn't blur the button first.
