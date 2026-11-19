# Handoff requests (desk_*_handoff_request)

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags. This is not a
tempui-DSL file type: it is four MCP tools on the `desk` server, for
asking an agent working in another project (or a later session of this
one) to make a change, instead of editing that project yourself.

A request has the lifecycle `new` -> `in-progress` -> `complete`.

- `desk_create_handoff_request(title, what, why?, constraints?,
  target_project?, requested_by?, directory?)` files a `new` request and
  returns it (including its `id`).
- `desk_list_handoff_requests(status?, keyword?, directory?)` lists
  requests, newest first. List with a keyword before filing, to avoid a
  near-duplicate.
- `desk_claim_handoff_request(id, claimed_by?, directory?)` moves a `new`
  request to `in-progress`. **Claim before touching anything.** It fails
  if someone else already claimed it; pick another.
- `desk_complete_handoff_request(id, outcome, note?, directory?)` closes
  an `in-progress` request. `outcome` is `done`, `partial`, `declined` or
  `not-applicable`; put what actually happened in `note` (for example,
  that part of the request rested on a false premise and was not
  implemented).

`directory` is where the requests live, **relative to the current
project** (default `handoff-requests`; `../other-project/handoff-requests`
reaches a sibling project). Absolute paths are refused. The requester and
the agent doing the work must pass the same directory. Under it, each
request is a markdown file in a `new/`, `in-progress/` or `complete/`
subdirectory, with its structured fields as frontmatter.
