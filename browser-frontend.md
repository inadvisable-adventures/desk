# Browser/frontend conventions

Guidance for code that runs in a web browser (e.g. `kind: "html"`
widgets, web components).

- Always use TypeScript in strict mode.
- Prefer static type imports at the top of a file rather than inline
  ones.
- Avoid putting HTML and CSS directly in code that will run in the
  browser. Prefer `<template>` and `<slot>` where possible in web
  component code especially.
