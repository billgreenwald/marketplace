# marketplace

Bill Greenwald's [Claude Code](https://claude.com/claude-code) plugin marketplace.

## Add this marketplace

```
/plugin marketplace add billgreenwald/marketplace
```

## Plugins

### `finish-update`

Bumps a project's version (major/minor/bugfix/rev/branch), updates its changelog and docs, commits, tags, and pushes to git — optionally building and publishing a GitHub release, beta, or branch pre-release along the way.

Install:

```
/plugin install finish-update@marketplace
```

Use:

```
/finish-update minor release
```

See [`plugins/finish-update/skills/finish-update/SKILL.md`](plugins/finish-update/skills/finish-update/SKILL.md) for full behavior.

### `rich-render`

Writes plans, mathematical derivations, and logic or Bayes diagrams as rich HTML documents — LaTeX typeset with KaTeX, flowcharts drawn with Mermaid — served on localhost instead of mangled into terminal markdown. Triggers on its own; math always renders, plans and diagrams render when they are substantial.

Install:

```
/plugin install rich-render@marketplace
```

Use: nothing to type — ask for a plan or a derivation. To control it:

```
/rich-render status
/rich-render port 3005
/rich-render render <topic>
```

Runs offline (KaTeX, Mermaid and marked are vendored) on the Python standard library alone. See [`plugins/rich-render/README.md`](plugins/rich-render/README.md).

## Adding more plugins

Each plugin lives under `plugins/<name>/` with its own `.claude-plugin/plugin.json` manifest and `skills/`, `commands/`, or `agents/` directories, and is registered in `.claude-plugin/marketplace.json` at the repo root.
