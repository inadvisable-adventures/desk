/**
 * A small, generic, dependency-free PEG (Parsing Expression Grammar) engine:
 * parses a grammar *description* (a plain-text `.peg` file, in a standard PEG
 * surface syntax -- `Rule <- expr`, ordered choice `/`, sequence by
 * juxtaposition, `*`/`+`/`?` repetition, `&`/`!` lookahead, labeled captures
 * `name:expr`, literal strings, character classes, grouping) into an internal
 * `Grammar`, then interprets that `Grammar` against input text to produce an
 * AST whose every node carries its source span (`start`/`end`, byte offsets
 * into the original text) -- see
 * `../../grammar-ast-live-pane.md` for why source positions are a hard
 * requirement, not an add-later feature.
 *
 * This is deliberately NOT a code generator (it doesn't emit new source code
 * per grammar) -- it's a single generic interpreter, grammar-agnostic, driven
 * by a declarative rule table built once from the `.peg` text. That's enough
 * to honor the actual decision recorded in `grammar-ast-live-pane.md` (the
 * grammar is declared in a dedicated notation, not as hand-written parsing
 * functions/combinators) without the extra machinery of literally generating
 * and compiling new TypeScript per grammar -- a possible later step if this
 * engine's performance or ergonomics ever demand it, not needed to pressure
 * -test the idea.
 *
 * Scope, deliberately: no memoization/packrat caching, no cut operator, no
 * semantic actions embedded in the grammar text (every named rule implicitly
 * becomes an AST node of that rule's name; labeled sub-expressions become
 * named children) -- semantic checks (e.g. "is this identifier an allowed
 * variable name") are a separate tree-walk over the produced AST, not part of
 * the grammar at all. Error recovery is whole-parse-attempt granularity (one
 * parse either succeeds or fails at the first unrecoverable point) -- this
 * matches the line/statement-level recovery scope `grammar-ast-live-pane.md`
 * settled on, matching what every hand-rolled parser examined in the case
 * studies already does independently.
 */

// --- the grammar description's own AST (what parsing a .peg file produces) -

type GAtom =
  | { kind: "lit"; text: string }
  | { kind: "class"; ranges: Array<[string, string]>; chars: string[]; negate: boolean }
  | { kind: "ref"; name: string }
  | { kind: "group"; expr: GChoice }
  | { kind: "not"; atom: GAtom } // `!atom` -- negative lookahead, consumes nothing
  | { kind: "and"; atom: GAtom }; // `&atom` -- positive lookahead, consumes nothing

type GTerm = { label: string | null; atom: GAtom; rep: "" | "*" | "+" | "?" };
type GSeq = GTerm[];
type GChoice = GSeq[]; // ordered choice of sequences

export interface Grammar {
  rules: Map<string, GChoice>;
  start: string;
}

// --- parsing a .peg grammar description into the above ---------------------

class GrammarSyntaxError extends Error {}

function parseGrammarText(text: string): Grammar {
  let pos = 0;

  // Spaces/tabs and comments *within one line*, never crossing a newline --
  // a newline is handled separately by skipTrivia below, which needs to
  // decide whether crossing it is safe.
  function skipIntraLineTrivia(): void {
    for (;;) {
      const before = pos;
      while (pos < text.length && (text[pos] === " " || text[pos] === "\t" || text[pos] === "\r")) pos++;
      if (text[pos] === "#") {
        while (pos < text.length && text[pos] !== "\n") pos++;
      }
      if (pos === before) return;
    }
  }

  // Whether what immediately follows a newline at `offset` is a new rule
  // header (`Name <- ...`) or the end of input -- the one place this
  // grammar notation's "one line per rule" convention has to be respected
  // by the engine itself, since nothing else delimits one rule's own
  // right-hand side from the next rule's left-hand side.
  function looksLikeRuleBoundary(offset: number): boolean {
    const rest = text.slice(offset);
    return /^\s*[A-Za-z_][A-Za-z0-9_]*\s*<-/.test(rest) || /^\s*$/.test(rest);
  }

  // General-purpose skip: freely crosses all whitespace/comments, including
  // newlines -- for a caller that just wants "find the next real token,"
  // never for one that needs to tell a same-rule continuation apart from
  // the start of the next rule (see `peekAtRuleBoundary` below for that).
  function skipTrivia(): void {
    for (;;) {
      skipIntraLineTrivia();
      if (text[pos] !== "\n") return;
      pos++;
    }
  }

  // Non-mutating lookahead, starting from the CURRENT `pos`: true if only
  // intra-line trivia remains before either a rule boundary or end of
  // input. `parseSeq` (deciding whether the current rule's sequence has
  // ended) and `parseTerm` (deciding whether a `*`/`+`/`?` suffix could
  // still follow) both need this *before* committing to a skip --
  // `skipTrivia` above has no boundary awareness and will happily wander
  // from the end of one rule straight into the next rule's own name, which
  // is exactly what broke parsing this engine's own first real grammar
  // (`../formula.peg`, confirmed directly): checking for a `*`/`+`/`?`
  // after a sequence's last term found none, and the unconditional skip
  // that check used to do had already crossed into the next rule's header
  // by the time that was discovered, so the next loop iteration treated
  // that rule's own name as one more term of the *previous* rule.
  function peekAtRuleBoundary(): boolean {
    let p = pos;
    while (p < text.length && (text[p] === " " || text[p] === "\t" || text[p] === "\r")) p++;
    if (text[p] === "#") {
      while (p < text.length && text[p] !== "\n") p++;
    }
    if (p >= text.length) return true;
    if (text[p] !== "\n") return false;
    return looksLikeRuleBoundary(p + 1);
  }

  function fail(message: string): never {
    const line = text.slice(0, pos).split("\n").length;
    throw new GrammarSyntaxError(`grammar text, line ${line}: ${message}`);
  }

  function matchLit(s: string): boolean {
    skipTrivia();
    if (text.startsWith(s, pos)) {
      pos += s.length;
      return true;
    }
    return false;
  }

  function parseIdent(): string {
    skipTrivia();
    const m = /^[A-Za-z_][A-Za-z0-9_]*/.exec(text.slice(pos));
    if (!m) fail("expected an identifier");
    pos += m[0].length;
    return m[0];
  }

  function parseStringLiteral(): string {
    skipTrivia();
    const quote = text[pos];
    if (quote !== "'" && quote !== '"') fail("expected a quoted literal");
    pos++;
    let out = "";
    while (pos < text.length && text[pos] !== quote) {
      if (text[pos] === "\\" && pos + 1 < text.length) {
        out += text[pos + 1];
        pos += 2;
      } else {
        out += text[pos];
        pos++;
      }
    }
    if (text[pos] !== quote) fail("unterminated string literal");
    pos++;
    return out;
  }

  function parseCharClass(): GAtom {
    skipTrivia();
    if (text[pos] !== "[") fail("expected '['");
    pos++;
    let negate = false;
    if (text[pos] === "^") {
      negate = true;
      pos++;
    }
    const ranges: Array<[string, string]> = [];
    const chars: string[] = [];
    while (pos < text.length && text[pos] !== "]") {
      let c = text[pos];
      if (c === "\\" && pos + 1 < text.length) {
        c = text[pos + 1];
        pos += 2;
      } else {
        pos++;
      }
      if (text[pos] === "-" && text[pos + 1] !== "]") {
        pos++; // consume '-'
        let c2 = text[pos];
        if (c2 === "\\" && pos + 1 < text.length) {
          c2 = text[pos + 1];
          pos += 2;
        } else {
          pos++;
        }
        ranges.push([c, c2]);
      } else {
        chars.push(c);
      }
    }
    if (text[pos] !== "]") fail("unterminated character class");
    pos++;
    return { kind: "class", ranges, chars, negate };
  }

  function parseAtom(): GAtom {
    skipTrivia();
    if (text[pos] === "!") {
      pos++;
      return { kind: "not", atom: parseAtom() };
    }
    if (text[pos] === "&") {
      pos++;
      return { kind: "and", atom: parseAtom() };
    }
    if (text[pos] === "(") {
      pos++;
      const expr = parseChoice();
      if (!matchLit(")")) fail("expected ')'");
      return { kind: "group", expr };
    }
    if (text[pos] === "'" || text[pos] === '"') {
      return { kind: "lit", text: parseStringLiteral() };
    }
    if (text[pos] === "[") {
      return parseCharClass();
    }
    if (/[A-Za-z_]/.test(text[pos])) {
      return { kind: "ref", name: parseIdent() };
    }
    fail(`unexpected character ${JSON.stringify(text[pos])}`);
  }

  function parseTerm(): GTerm {
    skipTrivia();
    let label: string | null = null;
    const savedPos = pos;
    if (/[A-Za-z_]/.test(text[pos] || "")) {
      const maybeLabel = parseIdent();
      skipTrivia();
      if (text[pos] === ":") {
        pos++;
        label = maybeLabel;
      } else {
        pos = savedPos; // not a label after all -- back up, parseAtom will re-read it as a ref
      }
    }
    const atom = parseAtom();
    let rep: "" | "*" | "+" | "?" = "";
    // Check the lookahead BEFORE skipping -- skipTrivia() has no rule
    // -boundary awareness and would happily cross straight into the next
    // rule's own name while hunting for a "*"/"+"/"?" that isn't there.
    if (!peekAtRuleBoundary()) {
      skipTrivia();
      if (text[pos] === "*" || text[pos] === "+" || text[pos] === "?") {
        rep = text[pos] as "*" | "+" | "?";
        pos++;
      }
    }
    return { label, atom, rep };
  }

  function parseSeq(): GSeq {
    const terms: GTerm[] = [];
    for (;;) {
      if (peekAtRuleBoundary()) break; // same reasoning as parseTerm above
      skipTrivia();
      if (pos >= text.length) break;
      const c = text[pos];
      if (c === "/" || c === ")") break;
      if (/[A-Za-z_'"[!&(]/.test(c)) {
        terms.push(parseTerm());
      } else {
        break;
      }
    }
    return terms;
  }

  function parseChoice(): GChoice {
    const options: GSeq[] = [parseSeq()];
    for (;;) {
      skipTrivia();
      if (text[pos] === "/") {
        pos++;
        options.push(parseSeq());
      } else {
        break;
      }
    }
    return options;
  }

  const rules = new Map<string, GChoice>();
  let start: string | null = null;
  skipTrivia();
  while (pos < text.length) {
    const name = parseIdent();
    if (!matchLit("<-")) fail(`expected '<-' after rule name ${JSON.stringify(name)}`);
    const expr = parseChoice();
    rules.set(name, expr);
    if (start === null) start = name; // first rule declared is the start rule, PEG convention
    skipTrivia();
  }
  if (start === null) fail("grammar has no rules");
  return { rules, start };
}

// --- the produced AST (what interpreting a Grammar against input text yields)

export interface AstNode {
  type: string; // the rule name this node was produced for, or "token" for a leaf literal/class match
  start: number;
  end: number;
  text: string;
  children: Record<string, AstNode | AstNode[] | null>;
}

export interface ParseFailure {
  ok: false;
  pos: number; // the furthest position reached before failing
  expected: string[]; // what would have allowed progress past `pos`
  line: number;
  column: number;
}

export interface ParseSuccess {
  ok: true;
  node: AstNode;
  end: number; // where the match ended (callers should check this === input.length)
}

export type ParseResult = ParseSuccess | ParseFailure;

// --- the interpreter --------------------------------------------------------

class Interpreter {
  private furthest = -1;
  private expectedAt: Set<string> = new Set();

  constructor(private grammar: Grammar, private input: string) {}

  private note(pos: number, expected: string): void {
    if (pos > this.furthest) {
      this.furthest = pos;
      this.expectedAt = new Set([expected]);
    } else if (pos === this.furthest) {
      this.expectedAt.add(expected);
    }
  }

  private skipWs(pos: number): number {
    let p = pos;
    while (p < this.input.length && /\s/.test(this.input[p])) p++;
    return p;
  }

  /** null means "no match at this position" -- not an exception, since
   * ordered choice needs to cheaply try the next alternative. */
  private matchAtom(atom: GAtom, pos: number): { end: number; node: AstNode } | null {
    const input = this.input;
    if (atom.kind === "lit") {
      const p = this.skipWs(pos);
      if (input.startsWith(atom.text, p)) {
        const end = p + atom.text.length;
        return { end, node: { type: "token", start: p, end, text: atom.text, children: {} } };
      }
      this.note(p, JSON.stringify(atom.text));
      return null;
    }
    if (atom.kind === "class") {
      const p = this.skipWs(pos);
      if (p >= input.length) {
        this.note(p, "a character");
        return null;
      }
      const c = input[p];
      const inRanges = atom.ranges.some(([lo, hi]) => c >= lo && c <= hi);
      const inChars = atom.chars.indexOf(c) !== -1;
      const matched = atom.negate ? !(inRanges || inChars) : inRanges || inChars;
      if (!matched) {
        this.note(p, "a character matching the class");
        return null;
      }
      const end = p + 1;
      return { end, node: { type: "token", start: p, end, text: c, children: {} } };
    }
    if (atom.kind === "ref") {
      const p = this.skipWs(pos);
      return this.matchRule(atom.name, p);
    }
    if (atom.kind === "group") {
      return this.matchChoice(atom.expr, pos);
    }
    if (atom.kind === "not") {
      const r = this.matchAtom(atom.atom, pos);
      if (r !== null) return null; // lookahead matched -- negative lookahead fails
      return { end: pos, node: { type: "token", start: pos, end: pos, text: "", children: {} } };
    }
    if (atom.kind === "and") {
      const r = this.matchAtom(atom.atom, pos);
      if (r === null) return null;
      return { end: pos, node: { type: "token", start: pos, end: pos, text: "", children: {} } }; // consumes nothing
    }
    throw new Error("unreachable atom kind");
  }

  private matchTerm(
    term: GTerm,
    pos: number
  ): { end: number; captured: AstNode | AstNode[] | null; matchedAny: boolean } | null {
    if (term.rep === "") {
      const r = this.matchAtom(term.atom, pos);
      if (r === null) return null;
      return { end: r.end, captured: term.label !== null ? r.node : null, matchedAny: true };
    }
    if (term.rep === "?") {
      const r = this.matchAtom(term.atom, pos);
      if (r === null) return { end: pos, captured: term.label !== null ? null : null, matchedAny: false };
      return { end: r.end, captured: term.label !== null ? r.node : null, matchedAny: true };
    }
    // "*" or "+"
    const nodes: AstNode[] = [];
    let p = pos;
    for (;;) {
      const r = this.matchAtom(term.atom, p);
      if (r === null) break;
      if (r.end === p && nodes.length > 0) break; // guard against an infinite loop on a zero-width match
      nodes.push(r.node);
      p = r.end;
    }
    if (term.rep === "+" && nodes.length === 0) return null;
    return { end: p, captured: term.label !== null ? nodes : null, matchedAny: true };
  }

  private matchSeq(seq: GSeq, pos: number): { end: number; children: AstNode["children"] } | null {
    let p = pos;
    const children: AstNode["children"] = {};
    for (const term of seq) {
      const r = this.matchTerm(term, p);
      if (r === null) return null;
      p = r.end;
      if (term.label !== null) children[term.label] = r.captured;
    }
    return { end: p, children };
  }

  private matchChoice(choice: GChoice, pos: number): { end: number; node: AstNode } | null {
    for (const seq of choice) {
      const r = this.matchSeq(seq, pos);
      if (r !== null) {
        // A sequence that's a single, unlabeled bare rule-reference transparently
        // returns the referenced rule's own node (see module comment: dispatch-only
        // rules like `Primary <- Neg / Group / Vector / Number / Name` shouldn't
        // wrap every alternative in an extra "Primary" node).
        if (seq.length === 1 && seq[0].label === null && seq[0].rep === "" && seq[0].atom.kind === "ref") {
          const only = this.matchAtom(seq[0].atom, pos);
          if (only !== null) return { end: only.end, node: only.node };
        }
        const start = pos === r.end ? pos : this.skipWs(pos);
        return {
          end: r.end,
          node: { type: "__seq__", start, end: r.end, text: this.input.slice(start, r.end), children: r.children },
        };
      }
    }
    return null;
  }

  matchRule(name: string, pos: number): { end: number; node: AstNode } | null {
    const choice = this.grammar.rules.get(name);
    if (!choice) throw new Error(`grammar references undefined rule ${JSON.stringify(name)}`);
    const r = this.matchChoice(choice, pos);
    if (r === null) return null;
    // Give the node this rule's own name, unless matchChoice already
    // transparently returned a sub-rule's node (dispatch case above).
    const node: AstNode = r.node.type === "__seq__" ? { ...r.node, type: name } : r.node;
    return { end: r.end, node };
  }

  parse(startRule: string): ParseResult {
    const r = this.matchRule(startRule, 0);
    if (r === null) {
      const line = this.input.slice(0, Math.max(this.furthest, 0)).split("\n").length;
      const lastNl = this.input.lastIndexOf("\n", Math.max(this.furthest, 0) - 1);
      return {
        ok: false,
        pos: Math.max(this.furthest, 0),
        expected: Array.from(this.expectedAt),
        line,
        column: Math.max(this.furthest, 0) - lastNl,
      };
    }
    return { ok: true, node: r.node, end: r.end };
  }
}

export function compileGrammar(pegText: string): Grammar {
  return parseGrammarText(pegText);
}

/** Parses `input` against `grammar`'s start rule. Does NOT require consuming
 * the whole input (callers that care, e.g. "no trailing tokens", should check
 * `result.end === input.length` themselves on a ParseSuccess) -- kept
 * separate because "must consume everything" is a property of how a rule is
 * used, not of the engine itself. */
export function parse(grammar: Grammar, input: string): ParseResult {
  return new Interpreter(grammar, input).parse(grammar.start);
}
