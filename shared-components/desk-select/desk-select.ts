// A drop-in replacement for a native <select>, as a standalone custom
// element. Its dropdown is ordinary page content (position: fixed
// inside its own shadow root), never an OS-level popup -- a native
// <select> opens one, and under the zoomable/pannable Workspace Canvas
// it lands detached from the control. See this directory's README.md.

interface DeskSelectOption {
  value: string;
  label: string;
  disabled: boolean;
  selected: boolean;
}

class DeskSelect extends HTMLElement {
  static observedAttributes = ["disabled", "value"];

  private readonly button: HTMLButtonElement;
  private readonly labelEl: HTMLElement;
  private readonly list: HTMLElement;
  private readonly observer: MutationObserver;
  private items: DeskSelectOption[] = [];
  private index = -1;
  private activeIndex = -1;
  private isOpen = false;
  private typeahead = "";
  private typeaheadTimer = 0;
  private initialized = false;
  // A selectedIndex assigned before options exist (before connecting).
  private pendingIndex = -1;

  constructor() {
    super();
    const template = document.getElementById("desk-select-template");
    if (!(template instanceof HTMLTemplateElement)) {
      throw new Error(
        "desk-select-template not found -- paste template.html's <template> block into this document"
      );
    }
    const shadow = this.attachShadow({ mode: "open" });
    shadow.appendChild(template.content.cloneNode(true));
    this.button = shadow.querySelector(".button") as HTMLButtonElement;
    this.labelEl = shadow.querySelector(".label") as HTMLElement;
    this.list = shadow.querySelector(".list") as HTMLElement;

    this.button.addEventListener("click", () => this.toggle());
    this.button.addEventListener("keydown", (event) => this.onKeyDown(event));
    this.list.addEventListener("pointerdown", (event) => event.preventDefault());
    this.list.addEventListener("click", (event) => this.onListClick(event));
    this.list.addEventListener("pointermove", (event) => this.onListHover(event));
    this.observer = new MutationObserver(() => this.readOptions());
  }

  connectedCallback(): void {
    // An element cloned out of a <template> is inert, not upgraded: a
    // property assigned to it (`el.value = x`) lands as an own data
    // property that would shadow this class's accessors forever once the
    // element upgrades. Re-route each such value through the real setter
    // (the standard "upgrade property" pattern) before reading options.
    for (const name of ["value", "selectedIndex", "disabled"] as const) {
      if (Object.prototype.hasOwnProperty.call(this, name)) {
        const own = (this as unknown as Record<string, unknown>)[name];
        delete (this as unknown as Record<string, unknown>)[name];
        (this as unknown as Record<string, unknown>)[name] = own;
      }
    }
    this.observer.observe(this, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["value", "selected", "disabled", "label"],
    });
    this.readOptions();
    this.initialized = true;
  }

  disconnectedCallback(): void {
    this.observer.disconnect();
    this.close();
  }

  attributeChangedCallback(name: string, _old: string | null, value: string | null): void {
    if (name === "disabled") {
      this.button.disabled = value !== null;
      if (value !== null) {
        this.close();
      }
    } else if (name === "value" && this.initialized && value !== null) {
      this.value = value;
    }
  }

  // ---- public surface, mirroring <select> ----------------------------

  get value(): string {
    return this.items[this.index]?.value ?? "";
  }

  set value(next: string) {
    if (!this.initialized) {
      // No options read yet (not connected): remember it as the value
      // attribute, which readOptions() consults on connect.
      this.setAttribute("value", String(next));
      this.pendingIndex = -1;
      return;
    }
    this.index = this.items.findIndex((item) => item.value === next);
    this.render();
  }

  get selectedIndex(): number {
    return this.index;
  }

  set selectedIndex(next: number) {
    if (!this.initialized) {
      this.pendingIndex = next;
      this.removeAttribute("value");
      return;
    }
    this.index = next >= 0 && next < this.items.length ? next : -1;
    this.render();
  }

  get disabled(): boolean {
    return this.hasAttribute("disabled");
  }

  set disabled(next: boolean) {
    this.toggleAttribute("disabled", next);
  }

  get options(): readonly HTMLOptionElement[] {
    return Array.from(this.querySelectorAll("option"));
  }

  // ---- options --------------------------------------------------------

  private readOptions(): void {
    const previous = this.initialized ? this.value : null;
    this.items = this.options.map((option) => ({
      value: option.hasAttribute("value") ? (option.getAttribute("value") as string) : (option.textContent ?? "").trim(),
      label: (option.textContent ?? "").trim(),
      disabled: option.disabled,
      selected: option.hasAttribute("selected"),
    }));
    // An explicit value (the current selection, else the `value`
    // attribute) that matches no option selects nothing, like <select>;
    // only when nothing was specified at all does the default apply.
    const wanted = previous !== null && previous !== "" ? previous : this.getAttribute("value");
    let index = -1;
    if (this.pendingIndex >= 0) {
      index = this.pendingIndex < this.items.length ? this.pendingIndex : -1;
      this.pendingIndex = -1;
    } else if (wanted !== null) {
      index = this.items.findIndex((item) => item.value === wanted);
    } else {
      index = this.items.findIndex((item) => item.selected);
      if (index < 0) {
        index = this.items.findIndex((item) => !item.disabled);
      }
    }
    this.index = index;
    this.render();
  }

  private render(): void {
    this.labelEl.textContent = this.items[this.index]?.label ?? "";
    while (this.list.firstChild) {
      this.list.removeChild(this.list.firstChild);
    }
    this.items.forEach((item, i) => {
      const el = document.createElement("div");
      el.className = "option";
      el.id = `option-${i}`;
      el.setAttribute("role", "option");
      el.setAttribute("aria-selected", String(i === this.index));
      if (item.disabled) {
        el.setAttribute("aria-disabled", "true");
      }
      el.dataset.index = String(i);
      el.textContent = item.label;
      this.list.appendChild(el);
    });
    if (this.isOpen) {
      this.setActive(this.activeIndex);
      this.position();
    }
  }

  // ---- open / close ---------------------------------------------------

  private toggle(): void {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  private open(): void {
    if (this.isOpen || this.disabled || this.items.length === 0) {
      return;
    }
    this.isOpen = true;
    this.list.hidden = false;
    this.button.setAttribute("aria-expanded", "true");
    this.setActive(this.index >= 0 ? this.index : this.nextEnabled(-1, 1));
    this.position();
    document.addEventListener("pointerdown", this.onOutsidePointer, true);
    // Capture, so a scroll of any ancestor closes it -- a fixed list
    // would otherwise stay put while its control scrolls away.
    document.addEventListener("scroll", this.onOutsideScroll, true);
    window.addEventListener("resize", this.onResize);
  }

  private close(): void {
    if (!this.isOpen) {
      return;
    }
    this.isOpen = false;
    this.list.hidden = true;
    this.button.setAttribute("aria-expanded", "false");
    this.button.removeAttribute("aria-activedescendant");
    document.removeEventListener("pointerdown", this.onOutsidePointer, true);
    document.removeEventListener("scroll", this.onOutsideScroll, true);
    window.removeEventListener("resize", this.onResize);
  }

  private readonly onOutsidePointer = (event: Event): void => {
    if (!event.composedPath().includes(this)) {
      this.close();
    }
  };

  private readonly onOutsideScroll = (event: Event): void => {
    if (!event.composedPath().includes(this.list)) {
      this.close();
    }
  };

  private readonly onResize = (): void => this.close();

  // Below the control if it fits, else above, whichever side has more
  // room; the list scrolls itself when neither is enough.
  private position(): void {
    const rect = this.button.getBoundingClientRect();
    const margin = 8;
    const below = window.innerHeight - rect.bottom - margin;
    const above = rect.top - margin;
    const style = this.list.style;
    style.minWidth = `${rect.width}px`;
    style.left = `${Math.max(0, rect.left)}px`;
    style.maxHeight = "";
    style.top = `${rect.bottom + 2}px`;
    style.bottom = "";
    const natural = this.list.offsetHeight;
    if (natural <= below || below >= above) {
      style.maxHeight = `${Math.max(below, 60)}px`;
    } else {
      style.top = "";
      style.bottom = `${window.innerHeight - rect.top + 2}px`;
      style.maxHeight = `${Math.max(above, 60)}px`;
    }
    const overflowRight = this.list.getBoundingClientRect().right - window.innerWidth;
    if (overflowRight > 0) {
      style.left = `${Math.max(0, rect.left - overflowRight)}px`;
    }
  }

  // ---- selection ------------------------------------------------------

  private nextEnabled(from: number, step: 1 | -1): number {
    for (let i = from + step; i >= 0 && i < this.items.length; i += step) {
      if (!this.items[i].disabled) {
        return i;
      }
    }
    return from;
  }

  private setActive(index: number): void {
    this.activeIndex = index;
    for (const el of Array.from(this.list.children) as HTMLElement[]) {
      const isActive = Number(el.dataset.index) === index;
      el.toggleAttribute("data-active", isActive);
      if (isActive) {
        this.button.setAttribute("aria-activedescendant", el.id);
        el.scrollIntoView({ block: "nearest" });
      }
    }
  }

  private commit(index: number): void {
    if (index < 0 || this.items[index]?.disabled) {
      return;
    }
    const changed = index !== this.index;
    this.index = index;
    this.render();
    this.close();
    if (changed) {
      this.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
      this.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    }
  }

  private optionIndexOf(event: Event): number {
    const target = (event.target as HTMLElement | null)?.closest<HTMLElement>(".option");
    return target ? Number(target.dataset.index) : -1;
  }

  private onListClick(event: Event): void {
    this.commit(this.optionIndexOf(event));
  }

  private onListHover(event: Event): void {
    const index = this.optionIndexOf(event);
    if (index >= 0 && !this.items[index].disabled && index !== this.activeIndex) {
      this.setActive(index);
    }
  }

  private onKeyDown(event: KeyboardEvent): void {
    switch (event.key) {
      case "ArrowDown":
      case "ArrowUp": {
        event.preventDefault();
        if (!this.isOpen) {
          this.open();
          return;
        }
        this.setActive(this.nextEnabled(this.activeIndex, event.key === "ArrowDown" ? 1 : -1));
        return;
      }
      case "Home":
      case "End": {
        if (this.isOpen) {
          event.preventDefault();
          this.setActive(
            event.key === "Home" ? this.nextEnabled(-1, 1) : this.nextEnabled(this.items.length, -1)
          );
        }
        return;
      }
      case "Enter":
      case " ": {
        event.preventDefault();
        if (this.isOpen) {
          this.commit(this.activeIndex);
        } else {
          this.open();
        }
        return;
      }
      case "Escape": {
        if (this.isOpen) {
          event.preventDefault();
          this.close();
        }
        return;
      }
      case "Tab": {
        this.close();
        return;
      }
      default: {
        if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
          this.typeaheadSelect(event.key.toLowerCase());
        }
      }
    }
  }

  // Native-like type-ahead: repeated typing within 700 ms extends the
  // prefix; the first enabled match (searching from the next item for a
  // single repeated letter) becomes active, or selected if closed.
  private typeaheadSelect(char: string): void {
    window.clearTimeout(this.typeaheadTimer);
    this.typeahead += char;
    this.typeaheadTimer = window.setTimeout(() => (this.typeahead = ""), 700);
    const start = this.isOpen ? this.activeIndex : this.index;
    const order = this.items.map((_, i) => (start + 1 + i) % this.items.length);
    const prefix = this.typeahead;
    const single = prefix.length > 1 && prefix.split("").every((c) => c === prefix[0]) ? prefix[0] : prefix;
    const match = order.find(
      (i) => !this.items[i].disabled && this.items[i].label.toLowerCase().startsWith(single)
    );
    if (match === undefined) {
      return;
    }
    if (this.isOpen) {
      this.setActive(match);
    } else {
      this.commit(match);
    }
  }
}

customElements.define("desk-select", DeskSelect);
