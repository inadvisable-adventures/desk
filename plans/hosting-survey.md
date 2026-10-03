# Hosting survey for always-on Desk agent sessions (TODO `38b5bef`) (COMPLETED)

## Summary
Find the most sensible always-on home for Desk agent sessions: DreamHost (the
user's first preference, and the one whose restrictions worry them), AWS, GCP,
or a Mac mini on the user's own network.

## Affected files
`investigations/hosting-for-always-on-agent-sessions.md` (new; the deliverable),
`TODO.md`. No code.

## Approach
Web research with dated, linked sources; every claim about a provider's terms is
quoted or closely paraphrased with its URL and read date, and anything I could
not find is said so rather than inferred. It is a best-effort reading, not legal
advice. Cost figures are list prices read on the day, with assumptions stated.
Per provider: what it sells that could host a long-running `claude` session, the
cheapest suitable tier, what its terms say about long-running processes and
about AI software / model API calls, and open risks. Then the Mac mini
comparison (purchase, power, remote access, break-even vs cumulative VM cost at
1/2/3 years) and how each would be reached (SSH/tmux now, the remote session
daemon of TODO `be2ce4e` later).

## Verification
Not testable; the check is that each claim has a source and a date, and that the
note names what would change the recommendation.
