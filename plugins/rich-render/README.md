# rich-render

Writes plans, mathematical derivations, and logic diagrams as **rich HTML
documents served on localhost** instead of as plain markdown in the terminal —
so LaTeX is typeset and Mermaid diagrams are drawn, rather than mangled.

Terminal markdown turns `$P(A_1 \mid B_2)$` into italic soup and a flowchart
into an unreadable fence. This fixes that without you asking each time.

## Install

```
/plugin install rich-render@marketplace
```

## How it triggers

The skill activates on its own. The rules are deliberately asymmetric:

| Content | Behavior |
|---|---|
| **LaTeX-worthy math** — derivations, Bayes, distributions, linear algebra, complexity | **Always renders.** No size threshold. |
| **Plans** — implementation, migration, refactor, rollout | Renders at roughly 4+ steps, or with phases and decision points. |
| **Diagrams** — control flow, state machines, causal graphs, sequences | Renders at roughly 4+ nodes, or any branching or cycle. |
| Short answers, code edits, debugging narration | Stays in the terminal. |

Saying *"render this"* or *"show me that properly"* forces it, and keeps
rendering related follow-ups for the rest of the conversation.

The terminal still gets a two-to-five-line summary plus the URL — never just a
bare link, never the whole document. In plan mode the full plan still goes in
the approval prompt, since you must be able to approve without leaving the
terminal.

## Manual control

```
/rich-render                 # status: running? which port? how many documents?
/rich-render stop            # stop the server (documents on disk are kept)
/rich-render restart
/rich-render port 3005       # move to another port
/rich-render host 127.0.0.1  # restrict to this machine (default is 0.0.0.0)
/rich-render open            # list this session's document URLs
/rich-render prune 14        # delete sessions older than 14 days
/rich-render render <topic>  # force a rich document for anything
```

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `RICH_RENDER_PORT` | `3001` | Preferred port. If taken by something else, the next free port is used. |
| `RICH_RENDER_HOST` | `0.0.0.0` | Bind address. The default is reachable from other machines over VPN or LAN; set `127.0.0.1` to restrict to this machine. |
| `RICH_RENDER_HOME` | `~/.claude/rich-render` | Where documents and server state live. |
| `RICH_RENDER_PRUNE_DAYS` | `30` | Age at which old sessions are deleted on server start. |

## Behavior

- **Offline.** KaTeX, Mermaid and marked are vendored under `assets/`. Nothing
  is fetched at runtime; the plugin works on an airgapped machine.
- **No dependencies.** The server is Python standard library only — no pip, no
  uv, no virtualenv.
- **Reachable remotely.** Binds `0.0.0.0` by default and advertises a
  hostname- or LAN-IP-based URL, so you can read documents from another machine
  over VPN. Anyone who can reach the port can read every rendered document —
  set `RICH_RENDER_HOST=127.0.0.1` if you want it local-only.
- **Live updates.** Open pages poll every 1.5s and re-render in place, keeping
  scroll position — a revised plan updates in an already-open tab.
- **Never opens a browser.** It prints a URL and lets you click.
- **Documents persist** in `~/.claude/rich-render/sessions/<timestamp>-<project>/`,
  grouped by project, pruned after 30 days. The index at `/` lists them all.

## Layout

```
rich-render/
├── skills/rich-render/SKILL.md   # trigger rules + authoring guide
├── commands/rich-render.md       # /rich-render subcommands
├── server/
│   ├── serve.py                  # stdlib HTTP server + lifecycle CLI
│   ├── template.html             # document page
│   ├── index.html                # document index
│   ├── app.js                    # markdown -> math -> mermaid pipeline
│   └── style.css                 # theme-aware document styles
├── assets/                       # vendored KaTeX, Mermaid, marked (MIT)
└── tools/vendor.sh               # re-download vendored assets
```

## The math-in-markdown problem

Markdown eats `_` and `*` inside formulas, so `$P(A_1|B_2)$` renders as
mangled italics. `app.js` extracts math into placeholders **before** the
markdown parser runs, in a single left-to-right scan that also matches code
fences and inline code spans and passes them through untouched. So formulas
survive intact, while `` `echo $PATH` `` and `$5 and $10` are never mistaken
for math. Invalid LaTeX renders as red inline text instead of breaking the page.

## Server CLI

Usable directly, without Claude:

```bash
python3 server/serve.py start [--port N] [--host ADDR] [--project DIR] [--new-session]
python3 server/serve.py status
python3 server/serve.py stop
python3 server/serve.py run --port N     # foreground, for debugging
python3 server/serve.py prune --days 30
```

`start` is idempotent: it reuses a running server, reuses the project's session
directory for 12 hours, and returns JSON with the port, session directory, and
document URL base.
