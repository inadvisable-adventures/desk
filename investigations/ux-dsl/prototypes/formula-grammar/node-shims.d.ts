/**
 * Minimal ambient declarations for the handful of Node.js globals/modules
 * `run-pressure-test.ts` uses, so this prototype doesn't need to pull in
 * `@types/node` as a dependency (per `CLAUDE.md`: "avoid adding
 * dependencies, prefer bespoke solutions") just to run a test harness. Not
 * meant to be a general-purpose Node typings file -- only what's actually
 * used here.
 */

declare const console: { log(...args: unknown[]): void };
declare const process: { exit(code?: number): void };
declare const __dirname: string;

declare module "fs" {
  export function readFileSync(path: string, encoding: string): string;
}

declare module "path" {
  export function join(...parts: string[]): string;
}
