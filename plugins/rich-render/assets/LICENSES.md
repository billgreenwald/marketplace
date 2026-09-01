# Vendored third-party assets

rich-render serves these locally so it works with no network access. All three
are MIT licensed. Refresh them with `tools/vendor.sh`.

| Package | Version | License | Upstream |
|---------|---------|---------|----------|
| KaTeX   | see `katex/VERSION`   | MIT | https://github.com/KaTeX/KaTeX |
| Mermaid | see `mermaid/VERSION` | MIT | https://github.com/mermaid-js/mermaid |
| marked  | see `marked/VERSION`  | MIT | https://github.com/markedjs/marked |

Only the WOFF2 KaTeX fonts referenced by `katex.min.css` are vendored; every
browser that runs Mermaid supports WOFF2, so the WOFF and TTF fallbacks are
omitted to keep the plugin smaller.
