# document-editor-base

A base class for a `DefineWidget`/browser-kind widget that is, at heart,
"a file-backed document, named by a title that derives its path, with
auto-load and auto-save": `DocumentEditorBase<Doc>`, extended by your
own custom element. It owns the file lifecycle (title → path, create
-vs-load, restoring the last-open document, saving on edit) so your own
widget code never touches `desk.fs.*`/`desk.self.getLocalStorage`
directly and never re-derives this from scratch.

Extracted and generalized from a real, already-shipped implementation
(`necro-4x`'s `DomainAnalysisElement`) — the same file lifecycle its
`TerrainColorInitializer`/`TerrainTypesEditor`/`TokenTypesEditor`
independently converged on too. All of these hand-rolled this exact
shape from scratch, and hit the identical bug doing it: an unguarded
`desk.fs.writeFile` to a directory that didn't exist yet, which
rejected silently. That specific bug is now fixed unconditionally,
server-side (`desk.fs.writeFile` creates missing parent directories —
see `tempui-custom-widgets.md`'s Bridge API section) — this base class
exists for the other half of the problem: there's nothing to *reach
for* except writing the load/save/create/restore plumbing again, so it
keeps getting re-implemented (and re-debugged) per widget.

## When to use this

Your widget is fundamentally "type a title, get an editable document
that lives at a path derived from that title, auto-saved as you edit
it" — a notes editor, a structured-data editor (see `necro-4x`'s Domain
Analysis), anything shaped like that. If your widget's file needs are
more exotic (multiple files, a fixed path unrelated to any title, no
title at all), this isn't the right fit — reach for `desk.fs.*` directly.

## How to use it

**Recommended: copy `document-editor-base.ts`'s contents directly into
the top of your own widget's `.ts` file**, rather than keeping it as a
separate file in your own project's source tree. This isn't just the
"copy+paste+modify" option for its own sake — it's the *safe* option
here specifically: this project's own widget build script
(`build_widget.py`) concatenates every compiled `.js` file in a
widget's own build output in plain alphabetical filename order, not
dependency order. Since a subclass's `class Foo extends
DocumentEditorBase` needs the base class already defined by the time
that line runs (confirmed directly: it isn't, and throws
`ReferenceError: Cannot access 'DocumentEditorBase' before
initialization`, if the compiled output happens to concatenate in the
wrong order), keeping this as a genuinely separate file only works if
your own widget's `.ts` filename is verified to sort alphabetically
*after* `document-editor-base` — easy to get wrong, and silently, since
nothing catches it until the widget actually runs. Pasting the class
directly into your own single `.ts` file sidesteps this entirely (one
file, unambiguous order) and is the only version of "use this" that's
foolproof by construction.

Then:

```ts
interface MyDoc { title: string; /* ...whatever your document holds... */ }

class MyEditorElement extends DocumentEditorBase<MyDoc> {
  protected readonly directory = "my-docs"; // <directory>/<kebab-title>.<extension>
  protected readonly extension = "md";

  protected emptyDoc(title: string): MyDoc { return { title }; }
  protected parse(text: string, fallbackTitle: string): MyDoc { /* ... */ }
  protected serialize(doc: MyDoc): string { /* ... */ }

  protected onConnected(): void {
    // Attach your own shadow DOM/bind your own elements here -- called
    // once, before this base class does anything else. Wire your own
    // Create/Load buttons to `void this.create(titleValue)` /
    // `void this.load(titleValue)`, and call `void this.save()` after
    // every edit that should persist.
  }

  protected onEnterLocked(): void { /* show your editor UI */ }
  protected onEnterUnlocked(): void { /* show your title/create-or-load screen */ }
  protected onError(message: string): void { /* optional: show it visibly, not just console.error */ }
}

customElements.define("my-editor", MyEditorElement);
```

## What it handles for you

- **Path derivation**: `<directory>/<kebab-case(title)>.<extension>`.
- **Create vs. load — never silently clobbers**: `create(title)` refuses
  (via `onError`) if a document already exists at the derived path;
  `load(title)` fails clearly if nothing does.
- **Restoring the last-open document**: on connect, checks
  `desk.self.getLocalStorage()` for a remembered path and loads it
  automatically — falling back to the unlocked/blank state if that
  file's since been moved or deleted.
- **Save on edit**: call `this.save()` after each discrete edit action
  (matching every widget this was extracted from: *every* edit action
  saves immediately — there's no debounce timer, since there's nothing
  meaningful to save on a bare keystroke before some actual edit
  action, like adding a row or a tag, happens).
- **Visible errors**: failures call `onError` (default: `console.error`,
  which already surfaces through the `kind:"html"` titlebar `[ERROR]`
  indicator for free) rather than failing silently — override it to
  also show something in your own UI, the way the real widgets this was
  extracted from each did with their own error banner.

## What it deliberately doesn't do

No `export`/`import` anywhere in `document-editor-base.ts` — any
`import`/`export` makes TypeScript treat a file as a module with its
own file-scoped declaration space, which stops a global `interface
Window { desk?: ... }` augmentation from merging with the real global
`Window` type (confirmed directly). This project's build pipeline
concatenates plain global scripts, never real ES modules, matching
every real widget this was extracted from.
