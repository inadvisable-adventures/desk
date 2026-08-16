"""Data shapes for an app-structure DSL definition (TODO 48e3b39) --
see README.md (this same directory) for the full DSL format this
backs, and plans/app-structure-dsl.md (in the Desk repo this was
authored from) for the design this implements.

Deliberately plain dataclasses, not a JSON Schema library: `CLAUDE.md`
(the Desk repo this tool was authored alongside) prefers bespoke
solutions over new dependencies, and the validation this DSL actually
needs (required keys, known `type` discriminants, cross-references
that resolve to a declared component/state slot) is straightforward
enough to hand-write clear, specific error messages for -- see
parse.py."""

from dataclasses import dataclass, field


@dataclass
class ComponentEntry:
    """One entry in the DSL's component registry -- `tag` is the
    custom element's own tag name (e.g. "map-panel"), `source` is
    where its plain, Desk-unaware TypeScript source lives, relative to
    the components directory build.py is invoked with. `class_name` is
    only used by codegen's "global" mode (TODO 1e032f3), where there's
    no `import ... as Alias` step to rename the component's own
    declared class to whatever codegen expects -- None (the default)
    falls back to codegen's own deterministic tag-to-class-name
    derivation ("map-panel" -> "MapPanelElement"); set it explicitly
    if your component's real class name doesn't happen to match that."""

    tag: str
    source: str
    class_name: str | None = None


@dataclass
class SplitLayoutNode:
    """One node of an n-split-panes layout tree (DSL layout mode 1).
    `type` is "hsplit"/"vsplit" (internal node, `children` populated,
    `widget` None) or "pane" (leaf, `widget` names a component tag
    from the registry, `children` empty). `min_size`/`max_size` are
    optional per-node resize clamp values (pixels), meaningful only on
    a child of a split node -- mirrors the clamp-range wiring
    world-timelines already hand-writes for its own CSS custom
    properties."""

    type: str
    children: list["SplitLayoutNode"] = field(default_factory=list)
    widget: str | None = None
    min_size: float | None = None
    max_size: float | None = None


@dataclass
class WindowEntry:
    """One entry of a windowed layout (DSL layout mode 2) -- close to
    Desk's own `.desk`-file `WidgetState` shape on purpose (x/y/width/
    height, a widget reference), not yet implemented in codegen this
    pass (see plans/app-structure-dsl.md's Key tradeoffs)."""

    widget: str
    x: float
    y: float
    width: float
    height: float


@dataclass
class LayoutDefinition:
    """`type` is "split" (mode 1, codegen implemented this pass) or
    "windowed" (mode 2, schema-only this pass -- codegen raises a
    clear DslError rather than silently emitting wrong output). For
    "split": `variants` maps a variant name to its own layout tree,
    `default_variant` names which one is active at startup -- "N named
    static layout trees, switched by name at runtime" per the design
    (not a general runtime-computed tree). For "windowed": `windows`
    is a flat list, no variants concept yet."""

    type: str
    variants: dict[str, SplitLayoutNode] = field(default_factory=dict)
    default_variant: str | None = None
    windows: list[WindowEntry] = field(default_factory=list)


@dataclass
class StateMutationAction:
    """An event-wiring action that sets a declared state slot's value
    -- `target` names the state slot, `source_expr` is a raw JS/TS
    expression (e.g. "event.detail.id") evaluated in the generated
    listener's own scope, emitted into the generated code verbatim.
    No separate expression language: a DSL author already writes real
    TypeScript for components/handlers, so a small JS expression
    snippet here is proportionate, not a new thing to learn."""

    target: str
    source_expr: str


@dataclass
class CallAction:
    """An event-wiring action that calls a method on another
    component (fan-out target), or on an escape-hatch handler.
    `target` is either a registered component tag, or
    "escape:<handler name>" referencing `AppDefinition.handlers`.
    `args` are raw JS/TS expressions, same convention as
    StateMutationAction.source_expr."""

    target: str
    method: str
    args: list[str] = field(default_factory=list)


@dataclass
class EventWiringEntry:
    """One row of the event-wiring table -- `event` is the DOM
    CustomEvent name, `emitter` is the component tag (or a worker name
    declared in AppDefinition.workers) that dispatches it, `actions`
    fan out to one or more StateMutationAction/CallAction in declared
    order."""

    event: str
    emitter: str
    actions: list[StateMutationAction | CallAction] = field(default_factory=list)


@dataclass
class StateSlot:
    """A plain, directly-mutable app-level state slot -- `type` is a
    TypeScript type string emitted verbatim (e.g. "string | null"),
    `default` is a JSON-serializable default value. No derived/
    computed state this pass -- see plans/app-structure-dsl.md."""

    name: str
    type: str
    default: object = None


@dataclass
class HandlerRef:
    """The escape hatch (DSL inventory item 8) -- a named reference to
    a hand-written, never-generated TypeScript module + export,
    callable from an event action via CallAction(target="escape:<name>",
    ...)."""

    module: str
    export: str


@dataclass
class AppDefinition:
    components: list[ComponentEntry] = field(default_factory=list)
    layout: LayoutDefinition | None = None
    events: list[EventWiringEntry] = field(default_factory=list)
    state: list[StateSlot] = field(default_factory=list)
    handlers: dict[str, HandlerRef] = field(default_factory=dict)


class DslError(Exception):
    """Any problem with a DSL definition that should abort with a
    clear message -- mirrors _BUILD_WIDGET_SCRIPT's own BuildError
    shape (Desk repo, src/desk/temp_ui.py): caught once in build.py's
    main(), never elsewhere, so every failure path prints one clean
    line instead of a traceback."""
