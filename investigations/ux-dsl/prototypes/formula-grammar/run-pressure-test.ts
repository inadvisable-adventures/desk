/**
 * Pressure test for the grammar/AST-engine direction recorded in
 * ../../grammar-ast-live-pane.md: express the raycaster family's formula DSL
 * (the richest real grammar found in the case studies) as a declarative
 * `.peg` grammar (`./formula.peg`), run it through the generic engine
 * (`./peg-engine.ts`) plus a semantic tree-walk (`./semantic-check.ts`), and
 * check that it agrees with the real, independently hand-written checker
 * (`./oracle.ts`, copied verbatim from the real project) on every test case
 * below -- same accept/reject outcome, not necessarily the same error text
 * or detection point (one intentional divergence is documented in
 * semantic-check.ts's `checkName`).
 *
 * Run: npx tsc -p . && node dist/run-pressure-test.js
 */

import * as fs from "fs";
import * as path from "path";
import { compileGrammar } from "./peg-engine";
import { checkFormulaStatementViaGrammar } from "./semantic-check";
import { checkFormulaStatement, FORMULA_VARS_BY_MODE, FormulaMode } from "./oracle";

let passed = 0;
let failed = 0;

function check(name: string, condition: boolean): void {
  if (condition) {
    passed++;
    console.log(`PASS: ${name}`);
  } else {
    failed++;
    console.log(`FAIL: ${name}`);
  }
}

function oracleAccepts(line: string, mode: FormulaMode): boolean {
  try {
    checkFormulaStatement(line, FORMULA_VARS_BY_MODE[mode]);
    return true;
  } catch {
    return false;
  }
}

function grammarAccepts(grammar: ReturnType<typeof compileGrammar>, line: string, mode: FormulaMode): boolean {
  try {
    checkFormulaStatementViaGrammar(grammar, line, FORMULA_VARS_BY_MODE[mode]);
    return true;
  } catch {
    return false;
  }
}

// __dirname is dist/ at runtime (tsc's outDir); the .peg file lives one
// level up, alongside the .ts sources -- it's a grammar description, not
// something that needs compiling itself.
const grammarText = fs.readFileSync(path.join(__dirname, "..", "formula.peg"), "utf8");
const grammar = compileGrammar(grammarText);

interface Case {
  line: string;
  mode: FormulaMode;
  expectAccept: boolean;
  note: string;
}

const cases: Case[] = [
  { line: "color = surface * light", mode: "color", expectAccept: true, note: "plain assignment" },
  { line: "color.r = surface.r * light.r", mode: "color", expectAccept: true, note: "component assignment + dotted names" },
  { line: "color = color / max", mode: "postprocess", expectAccept: true, note: "postprocess mode default formula" },
  { line: "color = (surface + light) * 2", mode: "color", expectAccept: true, note: "parens + precedence" },
  { line: "color = <1,2,3>", mode: "color", expectAccept: true, note: "vector literal of numbers" },
  { line: "color = <surface, light, surface>", mode: "color", expectAccept: true, note: "vector literal of names" },
  { line: "each k: color.k = surface.k * light.k", mode: "color", expectAccept: true, note: "each-loop, component matches loop var" },
  { line: "color = -surface * -1", mode: "color", expectAccept: true, note: "unary negation" },
  { line: "color = log_color", mode: "postprocess", expectAccept: true, note: "mode-specific allowed var" },
  { line: "color = red", mode: "color", expectAccept: true, note: "bare color literal" },
  { line: "color = red + green", mode: "postprocess", expectAccept: true, note: "color literals allowed in any mode" },

  { line: "", mode: "color", expectAccept: false, note: "empty statement" },
  { line: "color", mode: "color", expectAccept: false, note: "missing '='" },
  { line: "color = ", mode: "color", expectAccept: false, note: "missing operand after '='" },
  { line: "color = unknownvar", mode: "color", expectAccept: false, note: "unknown name" },
  { line: "color.x = surface", mode: "color", expectAccept: false, note: "bad assignment-target component" },
  { line: "each r: color.r = surface", mode: "color", expectAccept: false, note: "loop var can't be named r/g/b" },
  { line: "each k: color.j = surface", mode: "color", expectAccept: false, note: "each target must match loop var" },
  { line: "color = surface.q", mode: "color", expectAccept: false, note: "bad dotted component" },
  { line: "color = red.r", mode: "color", expectAccept: false, note: "a color literal can't take a dotted component (divergent mechanism, same outcome)" },
  { line: "color = surface *", mode: "color", expectAccept: false, note: "trailing operator, incomplete expression" },
  { line: "foo = surface", mode: "color", expectAccept: false, note: "statement must start with 'color' or 'each'" },
  { line: "color = max", mode: "color", expectAccept: false, note: "postprocess-only var used in color mode" },
  { line: "color = surface @ light", mode: "color", expectAccept: false, note: "unexpected character" },
  { line: "color = 5.r", mode: "color", expectAccept: false, note: "a number literal can't take a dotted component either" },
];

for (const c of cases) {
  const oracle = oracleAccepts(c.line, c.mode);
  const generated = grammarAccepts(grammar, c.line, c.mode);
  check(
    `[${c.mode}] ${JSON.stringify(c.line)} -- ${c.note} (oracle=${oracle ? "accept" : "reject"})`,
    oracle === generated
  );
}

// Source-position check: the generic engine's whole point (beyond just
// accept/reject agreement) is that every AST node carries its real span in
// the original text -- confirm that directly for one accepted case, rather
// than just trusting it was wired up correctly.
{
  const line = "color = surface * light";
  const stmt = checkFormulaStatementViaGrammar(grammar, line, FORMULA_VARS_BY_MODE.color);
  const expr = stmt.children.expr as import("./peg-engine").AstNode;
  const head = expr.children.head as import("./peg-engine").AstNode; // Term
  const name = head.children.head as import("./peg-engine").AstNode; // Name ("surface")
  check(
    "AST node for 'surface' carries its real source span",
    name.type === "Name" && line.slice(name.start, name.end) === "surface" && name.start === line.indexOf("surface")
  );
  const tail = head.children.tail as import("./peg-engine").AstNode[];
  const lightName = tail[0].children.term as import("./peg-engine").AstNode;
  check(
    "AST node for 'light' carries its real source span",
    lightName.type === "Name" && line.slice(lightName.start, lightName.end) === "light" && lightName.start === line.indexOf("light")
  );
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
