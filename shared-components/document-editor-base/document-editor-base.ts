// A file-backed, title-to-path document editor base class: given a
// directory and an extension, derives <directory>/<kebab-case(title)>
// .<extension> from a title, and handles create/load (never silently
// clobbering an existing file), auto-restoring the last-open document
// on mount, and save-on-edit -- see this directory's own README.md for
// how to extend it, and for what's specifically non-obvious below.
//
// Extracted and generalized from a real, already-shipped implementation
// (necro-4x's DomainAnalysisElement, plus the same file-lifecycle shape
// independently converged on by its TerrainColorInitializer,
// TerrainTypesEditor, and TokenTypesEditor) -- all four hand-rolled
// this exact lifecycle from scratch, and all four (or their siblings)
// hit the same missing-directory desk.fs.writeFile bug at some point
// (see TODO ad20867, which fixes that specific bug server-side --
// unconditionally, whether or not a widget uses this base class at
// all). This base class exists for the *other* half of that feedback:
// there's nothing to reach for except writing this lifecycle again
// from scratch, so it gets subtly re-implemented (and re-debugged)
// every time.

interface Window {
  desk?: {
    self: {
      getLocalStorage(): Promise<{ data: Record<string, unknown> }>;
      setLocalStorage(data: Record<string, unknown>): Promise<{ ok: boolean }>;
    };
    fs: {
      readFile(path: string): Promise<{ contents: string }>;
      writeFile(path: string, contents: string): Promise<{ ok: boolean }>;
    };
  };
}

function kebabCase(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Extend this, implement the abstract members, and call `create`/`load`
 * from your own UI (e.g. a title `<input>` plus Create/Load buttons) and
 * `save()` after every edit that should persist. See README.md.
 *
 * Deliberately not `export`ed: any `import`/`export` in a file makes
 * TypeScript treat it as a module with its own file-scoped declaration
 * space, which stops this file's own `interface Window` above from
 * merging with the real global `Window` type (confirmed directly --
 * `export`ing this class alone was enough to make `window.desk` stop
 * type-checking entirely). This project's whole build pipeline
 * (`build_widget.py`) concatenates compiled `.js` files into one plain
 * global `<script>` anyway, never real ES modules -- matching every
 * real widget this was extracted from, none of which use `export`/
 * `import` either.
 */
abstract class DocumentEditorBase<Doc> extends HTMLElement {
  // Real values assigned in connectedCallback, not the constructor --
  // custom element constructors take no arguments (the browser always
  // calls `new YourElement()` bare, even during upgrade), so anything
  // that needs a subclass's own directory/extension/emptyDoc()
  // (an overridden method, unsafe to call from the *base* constructor
  // before a subclass's own field initializers have necessarily run)
  // has to wait until connectedCallback fires instead.
  protected doc!: Doc;
  protected path = "";
  protected locked = false;

  // --- must be implemented by the subclass --------------------------------

  /** Where documents of this kind live, e.g. "domain-analysis". */
  protected abstract readonly directory: string;
  /** File extension, no leading dot, e.g. "md". */
  protected abstract readonly extension: string;

  protected abstract emptyDoc(title: string): Doc;
  protected abstract parse(text: string, fallbackTitle: string): Doc;
  protected abstract serialize(doc: Doc): string;

  /** Attach your own shadow DOM/bind your own elements here -- called
   * once, before this base class does anything else (including
   * restoring the last-open document, which may call onEnterLocked/
   * onEnterUnlocked below, so your own DOM must already exist by the
   * time this returns). */
  protected abstract onConnected(): void;

  // --- may be overridden by the subclass -----------------------------------

  /** Called whenever locked becomes true (a document was just created,
   * loaded, or restored) -- update your own DOM to show the editor. */
  protected onEnterLocked(): void {}

  /** Called whenever locked becomes false (no document is open yet, or
   * the remembered one couldn't be restored) -- update your own DOM to
   * show the title/create-or-load screen. */
  protected onEnterUnlocked(): void {}

  /** A create/load/save failure -- default just logs (surfaces via the
   * kind:"html" titlebar [ERROR] indicator, TODO d4d6c71, for free,
   * since that's wired to captured console errors already). Override
   * to also show a visible in-widget message. */
  protected onError(message: string): void {
    console.error(`DocumentEditorBase: ${message}`);
  }

  // --- path derivation / lifecycle -----------------------------------------

  protected pathForTitle(title: string): string {
    return `${this.directory}/${kebabCase(title)}.${this.extension}`;
  }

  protected async fileExists(path: string): Promise<boolean> {
    const desk = window.desk;
    if (!desk) return false;
    try {
      await desk.fs.readFile(path);
      return true;
    } catch {
      return false;
    }
  }

  connectedCallback(): void {
    this.doc = this.emptyDoc("");
    this.onConnected();
    void this.restoreAndInit();
  }

  /** Tries to restore the last-open document (its path remembered via
   * desk.self.getLocalStorage) -- falls back to the unlocked/blank
   * state if there wasn't one, or it's since been moved/deleted. */
  protected async restoreAndInit(): Promise<void> {
    const desk = window.desk;
    if (!desk) return;
    const { data } = await desk.self.getLocalStorage();
    const activePath = typeof data.activePath === "string" ? data.activePath : null;
    if (activePath) {
      try {
        const { contents } = await desk.fs.readFile(activePath);
        this.path = activePath;
        this.doc = this.parse(contents, "");
        this.locked = true;
        this.onEnterLocked();
        return;
      } catch {
        // Remembered file is gone/unreadable -- fall through below.
      }
    }
    this.switchToUnlocked();
  }

  protected switchToUnlocked(): void {
    this.locked = false;
    this.doc = this.emptyDoc("");
    this.path = "";
    this.onEnterUnlocked();
  }

  /** Creates a brand-new document at the path derived from `title`.
   * Refuses (via onError) if a document already exists there -- never
   * silently clobbers; use load() for that path instead. Returns
   * whether it succeeded. */
  protected async create(title: string): Promise<boolean> {
    if (!title.trim()) {
      this.onError("Enter a title first.");
      return false;
    }
    const path = this.pathForTitle(title);
    if (await this.fileExists(path)) {
      this.onError(`A document already exists at ${path} -- load it instead.`);
      return false;
    }
    this.path = path;
    this.doc = this.emptyDoc(title);
    this.locked = true;
    await this.persistActivePath();
    this.onEnterLocked();
    await this.save();
    return true;
  }

  /** Loads the existing document at the path derived from `title`.
   * Fails (via onError) if nothing exists there. Returns whether it
   * succeeded. */
  protected async load(title: string): Promise<boolean> {
    if (!title.trim()) {
      this.onError("Enter a title first.");
      return false;
    }
    const path = this.pathForTitle(title);
    const desk = window.desk;
    if (!desk) return false;
    try {
      const { contents } = await desk.fs.readFile(path);
      this.doc = this.parse(contents, title);
      this.path = path;
      this.locked = true;
      await this.persistActivePath();
      this.onEnterLocked();
      return true;
    } catch {
      this.onError(`No document found at ${path}.`);
      return false;
    }
  }

  /** Writes the current in-memory document to disk -- call this after
   * every edit that should persist (matching the real widgets this was
   * extracted from: every discrete edit action calls this immediately,
   * not a debounce timer -- there's nothing per-keystroke to save
   * before some discrete action, like adding a tag or a row, actually
   * happens). A failure calls onError rather than throwing, so a
   * caller can `void this.save()` a fire-and-forget call the same way
   * every widget this was extracted from already does. */
  protected async save(): Promise<void> {
    const desk = window.desk;
    if (!desk) return;
    try {
      await desk.fs.writeFile(this.path, this.serialize(this.doc));
    } catch (err) {
      this.onError(`Couldn't save to ${this.path}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  private async persistActivePath(): Promise<void> {
    const desk = window.desk;
    if (!desk) return;
    await desk.self.setLocalStorage({ activePath: this.path });
  }
}
