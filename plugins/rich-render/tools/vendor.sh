#!/usr/bin/env bash
# Re-download the vendored KaTeX / Mermaid / marked assets.
# Everything rich-render serves lives in assets/ so the plugin works offline.
set -euo pipefail

cd "$(dirname "$0")/.."
KATEX_VERSION="${KATEX_VERSION:-0.16.22}"
MERMAID_SPEC="${MERMAID_SPEC:-11}"
MARKED_SPEC="${MARKED_SPEC:-15}"

resolve() {
  curl -sfL "https://data.jsdelivr.com/v1/packages/npm/$1/resolved?specifier=$2" \
    | grep -oE '"version":[[:space:]]*"[^"]+"' | grep -oE '[0-9][^"]*'
}

echo "==> katex ${KATEX_VERSION}"
mkdir -p assets/katex/fonts
for f in katex.min.css katex.min.js; do
  curl -sfL -o "assets/katex/$f" "https://cdn.jsdelivr.net/npm/katex@${KATEX_VERSION}/dist/$f"
done
grep -oE 'fonts/KaTeX_[A-Za-z0-9-]+\.woff2' assets/katex/katex.min.css | sed 's|fonts/||' | sort -u \
  | while read -r font; do
      curl -sfL -o "assets/katex/fonts/$font" \
        "https://cdn.jsdelivr.net/npm/katex@${KATEX_VERSION}/dist/fonts/$font"
    done
echo "$KATEX_VERSION" > assets/katex/VERSION

MERMAID_VERSION="$(resolve mermaid "$MERMAID_SPEC")"
echo "==> mermaid ${MERMAID_VERSION}"
mkdir -p assets/mermaid
curl -sfL -o assets/mermaid/mermaid.min.js \
  "https://cdn.jsdelivr.net/npm/mermaid@${MERMAID_VERSION}/dist/mermaid.min.js"
echo "$MERMAID_VERSION" > assets/mermaid/VERSION

MARKED_VERSION="$(resolve marked "$MARKED_SPEC")"
echo "==> marked ${MARKED_VERSION}"
mkdir -p assets/marked
curl -sfL -o assets/marked/marked.min.js \
  "https://cdn.jsdelivr.net/npm/marked@${MARKED_VERSION}/marked.min.js"
echo "$MARKED_VERSION" > assets/marked/VERSION

# The mermaid UMD bundle must be self-contained; a build that lazily imports
# diagram chunks would break offline rendering.
if grep -q 'import("\./' assets/mermaid/mermaid.min.js; then
  echo "WARNING: mermaid bundle contains relative dynamic imports — not offline-safe" >&2
  exit 1
fi

echo
echo "vendored:"
echo "  katex   $(cat assets/katex/VERSION)   ($(ls assets/katex/fonts | wc -l) fonts)"
echo "  mermaid $(cat assets/mermaid/VERSION)"
echo "  marked  $(cat assets/marked/VERSION)"
du -sh assets
