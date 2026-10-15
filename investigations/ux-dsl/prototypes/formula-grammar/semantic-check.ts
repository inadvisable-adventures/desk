/**
 * Semantic validation over the AST `peg-engine.ts` produces from
 * `formula.peg` -- "which names are allowed where" is NOT part of the
 * grammar (mode-scoped allowlists, color literals, the assignment target's
 * component rules, and a loop variable's scope inside an `each` statement
 * are all semantic, not syntactic), so this is a separate tree-walk, kept
 * deliberately decoupled from parsing. This is itself one of the
 * architectural points this pressure test is checking: the real hand-rolled
 * `FormulaSyntaxChecker` (`oracle.ts`) interleaves syntax and semantics in
 * one recursive-descent pass; here they're two independent stages (parse to
 * an AST, then walk it) because the grammar/AST engine only ever produces
 * syntax trees, nothing else.
 *
 * Mirrors `oracle.ts`'s `checkFormulaStatement`/`FormulaSyntaxChecker`
 * exactly in *outcome* (same inputs accepted/rejected), with one
 * intentional, noted divergence in *mechanism*: see `checkName` below.
 */

import { AstNode, Grammar, parse } from "./peg-engine";
import { COLORS } from "./oracle";

function skipWsFrom(s: string, pos: number): number {
  let p = pos;
  while (p < s.length && /\s/.test(s[p])) p++;
  return p;
}

function text(node: AstNode | AstNode[] | null | undefined): string {
  if (!node || Array.isArray(node)) throw new Error("internal: expected a single AST node, not an array/null");
  return node.text;
}

function one(node: AstNode | AstNode[] | null | undefined): AstNode {
  if (!node || Array.isArray(node)) throw new Error("internal: expected a single AST node, not an array/null");
  return node;
}

function many(node: AstNode | AstNode[] | null | undefined): AstNode[] {
  if (node === null || node === undefined) return [];
  if (!Array.isArray(node)) throw new Error("internal: expected an array of AST nodes");
  return node;
}

/** Throws on the first problem found, exactly like `oracle.ts`'s
 * `checkFormulaStatement` -- the grammar-engine-based replacement for it. */
export function checkFormulaStatementViaGrammar(grammar: Grammar, line: string, allowedVars: string[]): AstNode {
  const result = parse(grammar, line);
  if (!result.ok) {
    throw new Error(
      `line ${result.line}, column ${result.column}: expected one of ${result.expected.join(", ")}`
    );
  }
  const trailingStart = skipWsFrom(line, result.end);
  if (trailingStart !== line.length) {
    throw new Error("unexpected trailing tokens");
  }
  const stmt = result.node;
  if (stmt.type === "EachStatement") {
    checkEachStatement(stmt);
  } else if (stmt.type === "AssignStatement") {
    checkAssignStatement(stmt, allowedVars);
  } else {
    throw new Error(`internal: unexpected top-level node type ${stmt.type}`);
  }
  return stmt;

  function checkEachStatement(stmt: AstNode): void {
    const loopVar = text(stmt.children.loopVar);
    if (loopVar === "r" || loopVar === "g" || loopVar === "b") {
      throw new Error("the loop variable in 'each <var>: ...' can't be named r, g, or b");
    }
    const target = text(stmt.children.target);
    if (target !== loopVar) {
      throw new Error(`an 'each ${loopVar}: ...' statement must assign to 'color.${loopVar}'`);
    }
    checkExpr(one(stmt.children.expr), allowedVars, loopVar);
  }

  function checkAssignStatement(stmt: AstNode, allowedVars: string[]): void {
    const dot = stmt.children.dot as AstNode | null;
    if (dot) {
      const comp = text(dot.children.comp);
      if (comp !== "r" && comp !== "g" && comp !== "b") {
        throw new Error("expected 'color.r', 'color.g', or 'color.b'");
      }
    }
    checkExpr(one(stmt.children.expr), allowedVars, null);
  }

  function checkExpr(expr: AstNode, allowedVars: string[], loopVar: string | null): void {
    checkTerm(one(expr.children.head), allowedVars, loopVar);
    for (const item of many(expr.children.tail)) {
      checkTerm(one(item.children.term), allowedVars, loopVar);
    }
  }

  function checkTerm(term: AstNode, allowedVars: string[], loopVar: string | null): void {
    checkPrimary(one(term.children.head), allowedVars, loopVar);
    for (const item of many(term.children.tail)) {
      checkPrimary(one(item.children.term), allowedVars, loopVar);
    }
  }

  // `Primary <- Neg / Group / Vector / Number / Name` is a dispatch-only
  // rule (see peg-engine.ts's module comment on transparent single-ref
  // alternatives) -- the node handed in here always has one of these five
  // concrete types directly, never type "Primary" itself.
  function checkPrimary(node: AstNode, allowedVars: string[], loopVar: string | null): void {
    switch (node.type) {
      case "Neg":
        checkPrimary(one(node.children.value), allowedVars, loopVar);
        return;
      case "Group":
        checkExpr(one(node.children.value), allowedVars, loopVar);
        return;
      case "Vector":
        checkExpr(one(node.children.x), allowedVars, loopVar);
        checkExpr(one(node.children.y), allowedVars, loopVar);
        checkExpr(one(node.children.z), allowedVars, loopVar);
        return;
      case "Number":
        return; // never evaluated, same as oracle.ts -- nothing to check
      case "Name":
        checkName(node, allowedVars, loopVar);
        return;
      default:
        throw new Error(`internal: unexpected Primary node type ${node.type}`);
    }
  }

  function checkName(node: AstNode, allowedVars: string[], loopVar: string | null): void {
    const name = text(node.children.id);
    const dot = node.children.dot as AstNode | null;
    if (COLORS.indexOf(name) !== -1) {
      // Divergence from oracle.ts, noted deliberately: the real hand-rolled
      // parser's IDENT branch returns immediately on a color literal,
      // *never even attempting* to consume a following '.' -- so
      // "color = red.r" is rejected there via a leftover-trailing-tokens
      // error one level up, not from inside parsePrimary. This grammar's
      // single shared Name rule has no such special case at parse time (the
      // grammar doesn't know a color literal from any other identifier --
      // that's exactly the point of keeping semantics out of the grammar),
      // so it syntactically consumes the dot and rejects it right here
      // instead. Same outcome (reject), different point/mechanism of
      // detection -- the pressure test checks outcomes, not which line
      // throws.
      if (dot) {
        throw new Error(
          `a color literal cannot have a dotted component (got ${JSON.stringify(name)}.${text(dot.children.comp)})`
        );
      }
      return;
    }
    if (name !== "color" && allowedVars.indexOf(name) === -1) {
      const known = Array.from(new Set([...allowedVars, "color"])).join(", ");
      throw new Error(`unknown name ${JSON.stringify(name)} (expected a color, or one of: ${known})`);
    }
    if (dot) {
      const comp = text(dot.children.comp);
      if (comp !== "r" && comp !== "g" && comp !== "b" && comp !== loopVar) {
        throw new Error(`unknown component ${JSON.stringify(comp)} (expected r, g, b, or the loop variable)`);
      }
    }
  }
}
