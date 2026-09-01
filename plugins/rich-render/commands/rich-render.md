---
name: rich-render
description: Control the rich-render document server — status, stop, port, render, open.
argument-hint: [status|stop|restart|port <n>|host <addr>|open|prune|render <topic>]
allowed-tools: Bash(python3:*), Write, Read, Glob
---

# /rich-render

Subcommand: **$1**  ·  Argument: **$2**

`SERVE="${CLAUDE_PLUGIN_ROOT}/server/serve.py"` in the commands below.

Dispatch on `$1`:

## (empty) or `status`

```bash
python3 "$SERVE" status
```

Report: running or not, the bind host, the port, the URL, and a count of
documents by session.
If it is not running, say so and note that it starts automatically the next
time a document is rendered. Do not start it just to report status.

## `stop`

```bash
python3 "$SERVE" stop
```

Confirm what was stopped. Documents on disk are untouched.

## `restart`

```bash
python3 "$SERVE" stop && python3 "$SERVE" start --project "$PWD"
```

Report the new URL.

## `port <n>`

`$2` is the port number. Validate it is an integer in 1024–65535; if not, say
so and stop.

```bash
python3 "$SERVE" start --port "$2" --project "$PWD"
```

This retires any server already serving this home and moves to the new port.
Report the new URL, and mention that `export RICH_RENDER_PORT=$2` makes it the
default for future sessions.

## `host <addr>`

`$2` is a bind address — `0.0.0.0` for all interfaces (the default, reachable
from other machines), `127.0.0.1` for this machine only, or a specific
interface IP.

```bash
python3 "$SERVE" start --host "$2" --project "$PWD"
```

The bind address is fixed when the socket opens, so this restarts the server.
Report the new URL, and mention that `export RICH_RENDER_HOST=$2` makes it the
default for future sessions.

## `open`

```bash
python3 "$SERVE" status
```

Print the index URL and the URLs of the current session's documents, newest
first, each with its title. Use the `url` field from the server verbatim — with
the default `0.0.0.0` bind it is a hostname or LAN IP that also works from
another machine. Do not open a browser.

## `prune [days]`

```bash
python3 "$SERVE" prune --days "${2:-30}"
```

Report which sessions were deleted.

## `render <topic>`

`$2` and everything after it describe what to render. This is an explicit
override: **render it regardless of size or type**, following the authoring
rules in the `rich-render` skill.

- If the topic refers to something already discussed in this conversation,
  render that content — do not re-derive or re-research it.
- If it names something new, produce the content first, then render it.
- If `$2` is empty, ask what to render.

Then keep rendering related follow-ups for the rest of the conversation.

## anything else

Show the available subcommands with one-line descriptions.
