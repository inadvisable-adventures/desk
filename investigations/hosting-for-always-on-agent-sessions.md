# Hosting for always-on Desk agent sessions

TODO `38b5bef`. Researched and written **2026-10-03**. Best-effort reading of
public pages, **not legal advice**. Every claim below is tagged with where it
came from; what I could not verify is listed under "Not verified". Prices are
list prices on the day (USD), not quotes, and several come from third-party
aggregator sites rather than the provider's own pricing page (marked *agg*).

## Goal

A place where Desk can keep agent (`claude`) sessions alive without the user
owning a machine that is always on and always connected. Providers considered:
DreamHost (first preference; the user is most worried about its restrictions),
AWS and GCP (acceptable), and a Mac mini on the user's own network.

## Recommendation (short)

1. **Ask DreamHost support in writing before committing**, then, if they are
   fine with it, run on a **DreamHost VPS (Stack 8 or Stack 4)**. Nothing I read
   restricts it (below), it is the cheapest always-on option, and it is the
   user's preferred vendor. The written answer is cheap insurance because the
   terms give DreamHost broad discretion to suspend.
2. **AWS or GCP small instance (~$12-25/month plus disk)** is the fallback if
   DreamHost says no or is flaky; same Linux, no policy worry I could find on the
   AWS side.
3. **A Mac mini only pays off over a long horizon** (break-even roughly 3+ years
   against a ~$24/month VM, ~7 years against a ~$12/month one) -- choose it for
   other reasons (macOS-specific tooling, wanting a home server for more than
   this, avoiding any provider-policy risk), not to save money.

What would change this: DreamHost support saying no; needing macOS (for example
to share the Seatbelt confinement of TODO `6e51e9f`, which a Linux VM would need
a separate bubblewrap/Landlock backend for); CPU/RAM needs bigger than assumed;
Anthropic clarifying subscription use on servers (below).

## The Anthropic side (applies to every option)

Source: Claude Code docs, "Legal and compliance"
(<https://code.claude.com/docs/en/legal-and-compliance>, read 2026-10-03).

- Running Claude Code on a hosted machine with **your own** subscription is not
  prohibited: the page says its restrictions do not prevent "an end user from
  signing in to the unmodified Claude Code binary with their own Claude
  subscription, including where a platform hosts Claude Code."
- Two cautions that matter for Desk specifically: (a) "Advertised usage limits
  for Pro and Max plans assume ordinary, individual usage of Claude Code **and
  the Agent SDK**" -- Desk drives the CLI through the Agent SDK, so always-on,
  multi-session use is where "ordinary individual usage" could be questioned;
  (b) developers building products "using the Agent SDK, should use API key
  authentication" and may not route other people through subscription
  credentials. Personal use under the user's own subscription is the case the
  page appears to permit, but I can't resolve the boundary for heavy unattended
  use; if it matters, ask Anthropic (the page points to sales).
- Unattended auth on a server: community guides describe `claude setup-token`
  (a long-lived token generated on the laptop, exported as
  `CLAUDE_CODE_OAUTH_TOKEN`) for Pro/Max (*third-party guides, e.g. the amux and
  virtua.cloud pages found by search; not verified against Anthropic's own
  docs*).
- **Remote Control** (<https://code.claude.com/docs/en/remote-control>) already
  lets a phone or browser drive a session "running on your machine", survives a
  laptop sleeping, and has a server mode (`claude remote-control`) that serves
  many sessions. But the session still runs on whichever machine hosts it, and
  in server mode "Claude Code gives up after roughly 10 minutes" of network
  outage and the process exits. It also surfaces sessions in claude.ai/the
  Claude app, not in Desk. So it removes some need for our own protocol but not
  the need for an always-on host; TODO `be2ce4e` should weigh using it versus a
  Desk-native daemon.

## DreamHost (read 2026-10-03)

Products: shared hosting, VPS, DreamCompute (cloud), dedicated.

- **Long-running processes.** Acceptable Use Policy
  (<https://www.dreamhost.com/legal/acceptable-use-policy/>): "With the
  exception of DreamHost Dedicated Servers, Cloud products, DreamPress
  instances, Managed VPS, and VPS instances, any process that opens a network
  socket to accept connections from external networks is prohibited." So
  **shared hosting is out**; VPS, Cloud/DreamCompute and Dedicated are
  exempt from that rule. (A `claude` session mostly makes *outbound* calls; the
  rule is about accepting connections, but shared hosting is the wrong product
  regardless.)
- **Resource use.** Same AUP, all products: "Any script or process that
  adversely affects the ability of any other customer to satisfactorily use their
  provided services, or that negatively impacts DreamHost infrastructure, is
  prohibited." A steady, mostly-idle agent session should be nowhere near this,
  but it is the clause to keep in mind.
- **AI.** The AUP does not mention artificial intelligence or machine
  learning. The Terms of Service
  (<https://www.dreamhost.com/legal/terms-of-service/>, shown as last updated
  2026-08-27 by the fetch tool) mention AI only for DreamHost's own tools
  (Remixer, the business-name generator) in the indemnification section; no
  rule about customers running AI software.
- **Discretion.** The ToS lets DreamHost "disable or suspend without refund any
  account or service at any time should it feel, in its sole discretion, that
  there is a reasonable suspicion that it is being used in violation of any
  agreed upon terms." This is the real residual risk -- not a stated rule but a
  broad right -- and is why the written confirmation is worth asking for.

**Plans and prices** (VPS page <https://www.dreamhost.com/hosting/vps/>; DreamCompute
billing <https://help.dreamhost.com/hc/en-us/articles/217744568-DreamCompute-billing>):

| Product | RAM / vCPU | Price |
|---|---|---|
| VPS Stack 4 | 4 GB / 2 | $5.99/mo for the first 2 years, renews at $10.99 |
| VPS Stack 8 | 8 GB / 2 | $9.49/mo first 2 years, renews at $14.99 |
| VPS Stack 16 | 16 GB / 4 | $15.49/mo first 2 years, renews at $23.49 |
| DreamCompute 2 GB | 2 GB / 1 | $12/mo cap ($0.02/h) |
| DreamCompute 4 GB | 4 GB / 2 | $24/mo cap ($0.04/h) |
| DreamCompute 8 GB | 8 GB / 4 | $48/mo cap ($0.08/h) |

VPS plans include full root and SSH. The promotional VPS price assumes a 2-year
term (the page's own stated assumption). DreamCompute bills hourly up to a
600-hour/month cap, includes 100 GB block storage, and says bandwidth is
"currently free but may change at DreamHost's discretion."

## AWS and GCP

- **AWS** (prices *agg*, us-east-1 on-demand): t4g.small ~$12.26/mo
  ($0.0168/h), t4g.medium ~$24.53/mo ($0.0336/h); plus EBS disk (a few $/month
  for tens of GB). AWS Acceptable Use Policy
  (<https://aws.amazon.com/aup/>, last updated 2021-07-01): does not mention
  AI/ML; the closest rule is the general ban on violating "the security,
  integrity, or availability" of systems -- nothing aimed at running an agent
  that calls an external API.
- **GCP** (prices *agg*, us-central1 on-demand): e2-small ~$12.23/mo, e2-medium
  ~$24.46/mo, e2-micro ~$6.11/mo (one e2-micro is in the always-free tier in US
  regions but is too small to be comfortable). **Not verified:** I could not read
  Google's Cloud Platform AUP with my tools, so I make no claim about it.
- Both are comparable in price to DreamCompute 2-4 GB and more expensive than the
  DreamHost VPS promo; their advantage is maturity and tooling, not cost.

## Mac mini on the user's own network

- The current M6 Mac mini starts at **$899** (16 GB / 256 GB), launched
  2026-08-25, shipping from 2026-09-22 (TechCrunch, AppleInsider via search; a
  review notes the base SSD is small). A previous-generation M4 mini launched
  at $599 -- current availability and price not verified.
- **Power:** idle draw is a few watts (reported 2.6-4 W for the M4 mini), i.e.
  roughly $0.5-$1/month at typical electricity prices; I use $1/month.
- **Making it behave as a server** is real setup work: community guides stress
  that macOS sleeps headless Macs and that `claude remote-control` is a
  foreground process, so you need sleep prevention, a supervisor (launchd) and
  a way in (Tailscale, SSH, tmux). Fine, but not zero effort.
- **Break-even versus a VM** (purchase / (VM monthly - $1 power)):

  | Compared against | $899 M6 mini | $599 M4 mini |
  |---|---|---|
  | $6/mo (DreamHost Stack 4 promo) | ~180 months | ~120 months |
  | $12/mo (small AWS/GCP, DreamCompute 2 GB) | ~82 months (6.8 yr) | ~54 months |
  | $24/mo (4 GB cloud instance) | ~39 months (3.3 yr) | ~26 months |
  | $48/mo (8 GB cloud instance) | ~19 months | ~13 months |

  Cloud is cheaper unless the user would otherwise buy 4-8 GB-class instances
  for years, or wants the mini for other reasons.

## How each would actually be reached

- **Now, without our own code:** SSH + tmux running `claude`, or
  `claude remote-control` server mode, plus the Claude app/claude.ai. Works on any
  option above; sessions do not appear inside Desk.
- **With Desk attached:** needs the remote session daemon of TODO `be2ce4e` (the
  `session_event` stream is the natural wire format). Cloud Linux hosts would
  also want TODOs `6e51e9f`/`172b236` (confinement) to have a Linux backend.

## Assumptions and not verified

- Sizing: I assumed 2-4 GB RAM is enough for a few concurrent `claude` sessions;
  I did not measure it.
- AWS and GCP prices come from aggregator sites; confirm on the providers' own
  pricing pages before buying.
- GCP's AUP and any Anthropic *commercial* terms (relevant only if API-key auth
  were used) were not read.
- Reading terms is not the same as DreamHost's current enforcement practice;
  hence the written confirmation.

## Sources (all read 2026-10-03)

- DreamHost AUP: https://www.dreamhost.com/legal/acceptable-use-policy/
- DreamHost ToS: https://www.dreamhost.com/legal/terms-of-service/
- DreamHost VPS: https://www.dreamhost.com/hosting/vps/
- DreamCompute billing: https://help.dreamhost.com/hc/en-us/articles/217744568-DreamCompute-billing
- Claude Code legal and compliance: https://code.claude.com/docs/en/legal-and-compliance
- Claude Code Remote Control: https://code.claude.com/docs/en/remote-control
- AWS AUP: https://aws.amazon.com/aup/
- AWS t4g prices (agg): https://www.economize.cloud/resources/aws/pricing/ec2/t4g.small/ , https://www.economize.cloud/resources/aws/pricing/ec2/t4g.medium/
- GCP e2 prices (agg): https://www.economize.cloud/resources/gcp/pricing/compute-engine/e2-small/ , https://www.economize.cloud/resources/gcp/pricing/compute-engine/e2-medium/
- Mac mini M6: https://techcrunch.com/2026/08/25/apples-latest-mac-mini-runs-on-a-new-m6-chip-and-starts-at-899/ , https://appleinsider.com/articles/26/08/25/m6-mac-mini-arrives-in-ram-and-ssd-constrained-environment
- Mac mini idle power: https://www.notebookcheck.net/Apple-Mac-Mini-M4-review-Smaller-faster-and-louder.918832.0.html
- Always-on Mac mini setups (community): https://guydevops.com/posts/always-on-claude-code-remote-control-mac-mini/ , https://jessemeria.com/blog/mac-mini-remote-dev-server
