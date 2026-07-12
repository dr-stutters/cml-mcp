# Cisco Validated Designs (CVD) library

A knowledge library of Cisco Validated Designs used to expand what the
specialist agents in [`.claude/agents/`](../.claude/agents/) know how to build
and validate. Each design gets its own subfolder holding the source materials
and a distilled, agent-consumable brief.

## How it works

- **One subfolder per design.** Drop the source files there — the Cisco CVD
  **PDF**, diagrams, etc. Binary sources (`*.pdf`, `*.pptx`, `*.docx`, `*.zip`,
  `*.vsdx`) are **gitignored**: they stay on your machine and are not committed,
  so the repo doesn't bloat.
- **`links.md`** in each folder records the web links (the Cisco doc URL and any
  related references).
- **`design-brief.md`** in each folder is the distilled, doc-grounded summary —
  written for an agent to read: scope, topology/components, config workflow,
  verification, and gotchas. This is the committed knowledge artifact.
- The relevant **specialist agent** is updated with a section for the design and
  a pointer to its `design-brief.md`, so its knowledge keeps growing.

## Index

| Design | Source | Status | Related agent |
|---|---|---|---|
| [Firewall SD-WAN](Firewall%20SD-WAN/) | [Cisco CVD](https://www.cisco.com/c/en/us/td/docs/security/secure-firewall/cvd/secure-firewall-sdwan-deployment-guide.html) | awaiting PDF (brief stub) | firewall-engineer |

## How to add a design

1. Create `Cisco Validated Designs/<Design Name>/`.
2. Drop the source files there (PDFs are auto-gitignored) and add the web
   link(s) to `links.md`.
3. Distill the source into `design-brief.md` — grounded in the document, no
   fabricated specifics. Cover: **Scope & when to use · Topology / components ·
   Config workflow · Verification · Gotchas.**
4. Update the relevant agent in `.claude/agents/`: add a section summarizing the
   design, a pointer to the `design-brief.md`, and extend the frontmatter
   `description` so the agent triggers on the design's keywords.
5. Add a row to the index table above.
