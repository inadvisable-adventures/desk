/**
 * Ground truth for the pressure test: a verbatim copy of the real,
 * independently hand-written formula-DSL checker this prototype is being
 * checked against -- NOT modified in any way (beyond adding `export` so
 * `run-pressure-test.ts` can import it; the original is a global script with
 * no import/export at all, see its own file's top comment for why).
 *
 * Copied from
 * draw-with-desk/desk_widgets/_raycaster-shared/raycaster-dsl.ts, lines
 * 148 (COLORS) and 538-750 (everything else), 2026-10-15. See
 * ../../grammar-ast-live-pane.md and
 * ../../widget-case-studies.md's raycaster-formula addendum for why this
 * grammar specifically was chosen as the pressure test.
 */

export const COLORS = ["red", "green", "blue", "white", "black"];

export type FormulaMode = "color" | "postprocess";

export const FORMULA_VARS_BY_MODE: Record<FormulaMode, string[]> = {
  color: ["surface", "light"],
  // log_color -- see main.py's own "Formula DSL" docstring section --
  // is a log-scaled color/max ratio (log1p(color)/log1p(max) per
  // channel), precomputed the same way max already is; this file only
  // ever validates a formula's own syntax (this section's own top
  // comment), so it just needs to know the name is legal here, not
  // compute anything with it.
  postprocess: ["color", "max", "log_color"],
};

export interface FormulaToken {
  kind: "NUMBER" | "IDENT" | "OP";
  value: string;
}

export const FORMULA_TOKEN_RE = /\s*(?:(\d+(?:\.\d+)?)|([A-Za-z_][A-Za-z0-9_]*)|([+\-*/=.,:()<>]))/y;

export function tokenizeFormulaLine(line: string): FormulaToken[] {
  const tokens: FormulaToken[] = [];
  FORMULA_TOKEN_RE.lastIndex = 0;
  let pos = 0;
  while (pos < line.length) {
    FORMULA_TOKEN_RE.lastIndex = pos;
    const m = FORMULA_TOKEN_RE.exec(line);
    if (!m || m.index !== pos) {
      if (line.slice(pos).trim() === "") break;
      throw new Error(`unexpected character ${JSON.stringify(line[pos])}`);
    }
    pos = FORMULA_TOKEN_RE.lastIndex;
    if (m[1] !== undefined) tokens.push({ kind: "NUMBER", value: m[1] });
    else if (m[2] !== undefined) tokens.push({ kind: "IDENT", value: m[2] });
    else tokens.push({ kind: "OP", value: m[3] });
  }
  return tokens;
}

/** Recursive-descent syntax check only -- returns nothing, throws on
 * the first problem, exactly mirroring main.py's own _FormulaParser
 * (see that file for the grammar this walks). */
export class FormulaSyntaxChecker {
  private pos = 0;
  constructor(
    private tokens: FormulaToken[],
    private allowedVars: string[],
    private loopVar: string | null
  ) {}

  private peek(): FormulaToken | null {
    return this.pos < this.tokens.length ? this.tokens[this.pos] : null;
  }

  private advance(): FormulaToken {
    const tok = this.peek();
    if (!tok) throw new Error("unexpected end of line");
    this.pos++;
    return tok;
  }

  private expectOp(value: string): void {
    const tok = this.advance();
    if (tok.kind !== "OP" || tok.value !== value) throw new Error(`expected ${JSON.stringify(value)}`);
  }

  parseExpr(): void {
    this.parseTerm();
    while (true) {
      const tok = this.peek();
      if (tok && tok.kind === "OP" && (tok.value === "+" || tok.value === "-")) {
        this.advance();
        this.parseTerm();
      } else {
        return;
      }
    }
  }

  private parseTerm(): void {
    this.parsePrimary();
    while (true) {
      const tok = this.peek();
      if (tok && tok.kind === "OP" && (tok.value === "*" || tok.value === "/")) {
        this.advance();
        this.parsePrimary();
      } else {
        return;
      }
    }
  }

  private parsePrimary(): void {
    const tok = this.peek();
    if (!tok) throw new Error("unexpected end of line");
    if (tok.kind === "OP" && tok.value === "-") {
      this.advance();
      this.parsePrimary();
      return;
    }
    if (tok.kind === "OP" && tok.value === "(") {
      this.advance();
      this.parseExpr();
      this.expectOp(")");
      return;
    }
    if (tok.kind === "OP" && tok.value === "<") {
      this.advance();
      this.parseExpr();
      this.expectOp(",");
      this.parseExpr();
      this.expectOp(",");
      this.parseExpr();
      this.expectOp(">");
      return;
    }
    if (tok.kind === "NUMBER") {
      this.advance();
      return;
    }
    if (tok.kind === "IDENT") {
      this.advance();
      const name = tok.value;
      if (COLORS.indexOf(name) !== -1) return;
      if (name !== "color" && this.allowedVars.indexOf(name) === -1) {
        const known = Array.from(new Set([...this.allowedVars, "color"])).join(", ");
        throw new Error(`unknown name ${JSON.stringify(name)} (expected a color, or one of: ${known})`);
      }
      const nxt = this.peek();
      if (nxt && nxt.kind === "OP" && nxt.value === ".") {
        this.advance();
        const compTok = this.advance();
        if (compTok.kind !== "IDENT") {
          throw new Error("expected a component after '.' (r, g, b, or the current loop variable)");
        }
        const comp = compTok.value;
        if (comp !== "r" && comp !== "g" && comp !== "b" && comp !== this.loopVar) {
          throw new Error(`unknown component ${JSON.stringify(comp)} (expected r, g, b, or the loop variable)`);
        }
      }
      return;
    }
    throw new Error(`unexpected token ${JSON.stringify(tok.value)}`);
  }

  atEnd(): boolean {
    return this.peek() === null;
  }
}

export function checkFormulaStatement(line: string, allowedVars: string[]): void {
  const tokens = tokenizeFormulaLine(line);
  if (tokens.length === 0) throw new Error("empty statement");

  if (tokens[0].kind === "IDENT" && tokens[0].value === "each") {
    if (tokens.length < 2 || tokens[1].kind !== "IDENT") throw new Error("expected 'each <var>: ...'");
    const loopVar = tokens[1].value;
    if (loopVar === "r" || loopVar === "g" || loopVar === "b") {
      throw new Error("the loop variable in 'each <var>: ...' can't be named r, g, or b");
    }
    let idx = 2;
    if (idx >= tokens.length || tokens[idx].kind !== "OP" || tokens[idx].value !== ":") {
      throw new Error("expected ':' after 'each <var>'");
    }
    idx++;
    if (idx >= tokens.length || tokens[idx].kind !== "IDENT" || tokens[idx].value !== "color") {
      throw new Error("an 'each' statement's target must be 'color'");
    }
    idx++;
    if (idx >= tokens.length || tokens[idx].kind !== "OP" || tokens[idx].value !== ".") {
      throw new Error(`expected 'color.${loopVar}' as the assignment target`);
    }
    idx++;
    if (idx >= tokens.length || tokens[idx].kind !== "IDENT" || tokens[idx].value !== loopVar) {
      throw new Error(`an 'each ${loopVar}: ...' statement must assign to 'color.${loopVar}'`);
    }
    idx++;
    if (idx >= tokens.length || tokens[idx].kind !== "OP" || tokens[idx].value !== "=") {
      throw new Error("expected '=' after the assignment target");
    }
    idx++;
    const checker = new FormulaSyntaxChecker(tokens.slice(idx), allowedVars, loopVar);
    checker.parseExpr();
    if (!checker.atEnd()) throw new Error("unexpected trailing tokens");
    return;
  }

  if (tokens[0].kind !== "IDENT" || tokens[0].value !== "color") {
    throw new Error("a formula statement must assign to 'color' or 'color.<r|g|b>'");
  }

  if (tokens.length >= 2 && tokens[1].kind === "OP" && tokens[1].value === ".") {
    if (
      tokens.length < 3 ||
      tokens[2].kind !== "IDENT" ||
      (tokens[2].value !== "r" && tokens[2].value !== "g" && tokens[2].value !== "b")
    ) {
      throw new Error("expected 'color.r', 'color.g', or 'color.b'");
    }
    if (tokens.length < 4 || tokens[3].kind !== "OP" || tokens[3].value !== "=") {
      throw new Error("expected '=' after 'color.<component>'");
    }
    const checker = new FormulaSyntaxChecker(tokens.slice(4), allowedVars, null);
    checker.parseExpr();
    if (!checker.atEnd()) throw new Error("unexpected trailing tokens");
    return;
  }

  if (tokens.length < 2 || tokens[1].kind !== "OP" || tokens[1].value !== "=") {
    throw new Error("expected '=' after 'color'");
  }
  const checker = new FormulaSyntaxChecker(tokens.slice(2), allowedVars, null);
  checker.parseExpr();
  if (!checker.atEnd()) throw new Error("unexpected trailing tokens");
}
