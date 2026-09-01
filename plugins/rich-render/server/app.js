/* rich-render — document renderer.
 *
 * Pipeline: markdown source -> mask code + extract math -> marked -> reinsert
 * KaTeX-rendered math -> mermaid.run() over ```mermaid fences.
 *
 * Math is extracted BEFORE marked runs, in a single code-aware left-to-right
 * scan, so markdown never gets to eat `_` or `*` inside a formula (the classic
 * `$P(A_1|B_2)$` -> mangled-italics bug). Code fences and inline code spans are
 * matched by the same scan and copied through untouched, so `$PATH` inside
 * backticks is never mistaken for math.
 */

const PLACEHOLDER_PREFIX = 'xrrmath';
const PLACEHOLDER_SUFFIX = 'xrr';

/* ------------------------------------------------------------------ */
/* front matter                                                        */
/* ------------------------------------------------------------------ */

function splitFrontMatter(src) {
  const match = /^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n?/.exec(src);
  if (!match) return { meta: {}, body: src };
  const meta = {};
  for (const line of match[1].split(/\r?\n/)) {
    const at = line.indexOf(':');
    if (at > 0 && !line.trimStart().startsWith('#')) {
      meta[line.slice(0, at).trim()] = line.slice(at + 1).trim().replace(/^["']|["']$/g, '');
    }
  }
  return { meta, body: src.slice(match[0].length) };
}

/* ------------------------------------------------------------------ */
/* math extraction                                                     */
/* ------------------------------------------------------------------ */

// Order matters: fenced code, then inline code, then display math, then inline.
const SCAN = new RegExp([
  /```[\s\S]*?(?:\r?\n[ \t]*```|$)/.source,   // fenced code (backticks)
  /~~~[\s\S]*?(?:\r?\n[ \t]*~~~|$)/.source,   // fenced code (tildes)
  /`+[^`]*`+/.source,                          // inline code span
  /\$\$[\s\S]+?\$\$/.source,                   // display math $$...$$
  /\\\[[\s\S]+?\\\]/.source,                   // display math \[...\]
  /\\\((?:[\s\S]+?)\\\)/.source,               // inline math \(...\)
  /\$(?![\s$])(?:\\.|[^$\\\n])+?\$(?!\d)/.source, // inline math $...$
].join('|'), 'g');

function extractMath(src) {
  const math = [];
  const out = src.replace(SCAN, (match) => {
    let tex = null;
    let display = false;

    if (match.startsWith('$$') && match.endsWith('$$') && match.length > 4) {
      tex = match.slice(2, -2);
      display = true;
    } else if (match.startsWith('\\[') && match.endsWith('\\]')) {
      tex = match.slice(2, -2);
      display = true;
    } else if (match.startsWith('\\(') && match.endsWith('\\)')) {
      tex = match.slice(2, -2);
    } else if (match.startsWith('$') && !match.startsWith('`')) {
      tex = match.slice(1, -1);
    }

    if (tex === null) return match;           // code — pass through untouched
    math.push({ tex, display });
    return `${PLACEHOLDER_PREFIX}${math.length - 1}${PLACEHOLDER_SUFFIX}`;
  });
  return { text: out, math };
}

function renderMath(entry) {
  if (!window.katex) return escapeHtml(entry.tex);
  try {
    return katex.renderToString(entry.tex, {
      displayMode: entry.display,
      throwOnError: false,
      strict: false,
      trust: false,
    });
  } catch (err) {
    return `<span class="math-error" title="${escapeHtml(String(err.message || err))}">${escapeHtml(entry.tex)}</span>`;
  }
}

function restoreMath(html, math) {
  if (!math.length) return html;
  // A display formula alone in a paragraph should replace the <p>, not nest in it.
  html = html.replace(
    new RegExp(`<p>\\s*${PLACEHOLDER_PREFIX}(\\d+)${PLACEHOLDER_SUFFIX}\\s*</p>`, 'g'),
    (whole, index) => (math[+index] && math[+index].display ? renderMath(math[+index]) : whole)
  );
  return html.replace(
    new RegExp(`${PLACEHOLDER_PREFIX}(\\d+)${PLACEHOLDER_SUFFIX}`, 'g'),
    (whole, index) => (math[+index] ? renderMath(math[+index]) : whole)
  );
}

/* ------------------------------------------------------------------ */
/* markdown                                                            */
/* ------------------------------------------------------------------ */

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

let markedReady = false;

function configureMarked() {
  if (markedReady) return;
  marked.use({
    gfm: true,
    breaks: false,
    renderer: {
      // marked >= 13 passes a token object; older versions pass (code, lang).
      code(codeOrToken, infoString) {
        const isToken = codeOrToken && typeof codeOrToken === 'object';
        const text = isToken ? codeOrToken.text : codeOrToken;
        const lang = ((isToken ? codeOrToken.lang : infoString) || '').trim().split(/\s+/)[0];
        if (lang === 'mermaid') {
          return `<pre class="mermaid">${escapeHtml(text)}</pre>`;
        }
        const cls = lang ? ` class="language-${escapeHtml(lang)}"` : '';
        return `<pre><code${cls}>${escapeHtml(text)}</code></pre>\n`;
      },
      // Wrap tables so wide ones scroll instead of blowing out the page.
      table(tokenOrHeader, bodyMaybe) {
        const isToken = tokenOrHeader && typeof tokenOrHeader === 'object';
        const inner = isToken
          ? renderTableToken.call(this, tokenOrHeader)
          : `<table><thead>${tokenOrHeader}</thead><tbody>${bodyMaybe || ''}</tbody></table>`;
        return `<div class="table-wrap">${inner}</div>\n`;
      },
    },
  });
  markedReady = true;
}

function renderTableToken(token) {
  const cell = (c, tag, align) => {
    const style = align ? ` style="text-align:${align}"` : '';
    return `<${tag}${style}>${this.parser.parseInline(c.tokens)}</${tag}>`;
  };
  const head = token.header
    .map((c, i) => cell.call(this, c, 'th', token.align[i]))
    .join('');
  const rows = token.rows
    .map((row) => `<tr>${row.map((c, i) => cell.call(this, c, 'td', token.align[i])).join('')}</tr>`)
    .join('');
  return `<table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
}

function markdownToHtml(body) {
  configureMarked();
  const { text, math } = extractMath(body);
  return restoreMath(marked.parse(text), math);
}

/* ------------------------------------------------------------------ */
/* theme                                                               */
/* ------------------------------------------------------------------ */

function storedTheme() {
  try { return localStorage.getItem('rich-render-theme'); } catch (e) { return null; }
}

function effectiveTheme() {
  const chosen = document.documentElement.getAttribute('data-theme');
  if (chosen) return chosen;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyStoredTheme() {
  const theme = storedTheme();
  if (theme === 'dark' || theme === 'light') {
    document.documentElement.setAttribute('data-theme', theme);
  }
}

function toggleTheme(onChange) {
  const next = effectiveTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('rich-render-theme', next); } catch (e) { /* private mode */ }
  if (onChange) onChange(next);
}

/* ------------------------------------------------------------------ */
/* mermaid                                                             */
/* ------------------------------------------------------------------ */

function initMermaid() {
  if (!window.mermaid) return;
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: effectiveTheme() === 'dark' ? 'dark' : 'default',
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    flowchart: { curve: 'basis', useMaxWidth: true },
    themeVariables: { fontSize: '14px' },
  });
}

async function runMermaid(root) {
  if (!window.mermaid) return;
  const nodes = Array.from(root.querySelectorAll('pre.mermaid:not([data-processed])'));
  if (!nodes.length) return;
  try {
    await mermaid.run({ nodes, suppressErrors: true });
  } catch (err) {
    console.warn('[rich-render] mermaid render failed', err);
  }
}

/* ------------------------------------------------------------------ */
/* toc                                                                 */
/* ------------------------------------------------------------------ */

function slugifyHeading(text, used) {
  let base = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'section';
  let slug = base;
  let n = 2;
  while (used.has(slug)) slug = `${base}-${n++}`;
  used.add(slug);
  return slug;
}

function buildToc(bodyEl, tocEl, shellEl) {
  const headings = Array.from(bodyEl.querySelectorAll('h2, h3'));
  const used = new Set();
  tocEl.innerHTML = '';
  if (headings.length < 3) {
    shellEl.classList.remove('has-toc');
    return [];
  }
  const inner = document.createElement('div');
  inner.className = 'toc-inner';
  inner.innerHTML = '<h4>Contents</h4>';
  for (const heading of headings) {
    if (!heading.id) heading.id = slugifyHeading(heading.textContent, used);
    const link = document.createElement('a');
    link.href = `#${heading.id}`;
    link.textContent = heading.textContent;
    if (heading.tagName === 'H3') link.className = 'lvl3';
    inner.appendChild(link);
  }
  tocEl.appendChild(inner);
  shellEl.classList.add('has-toc');
  return headings;
}

function trackToc(headings, tocEl) {
  if (!headings.length) return null;
  const links = new Map();
  tocEl.querySelectorAll('a').forEach((a) => links.set(a.getAttribute('href').slice(1), a));
  const onScroll = () => {
    let current = headings[0];
    for (const heading of headings) {
      if (heading.getBoundingClientRect().top <= 96) current = heading;
    }
    links.forEach((a) => a.classList.remove('active'));
    const active = links.get(current.id);
    if (active) active.classList.add('active');
  };
  onScroll();
  return onScroll;
}

/* ------------------------------------------------------------------ */
/* misc ui                                                             */
/* ------------------------------------------------------------------ */

function toast(message) {
  let el = document.querySelector('.toast');
  if (!el) {
    el = document.createElement('div');
    el.className = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('show'), 1800);
}

function relativeTime(iso) {
  const then = new Date(iso).getTime();
  if (!then) return '';
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(then).toLocaleDateString();
}

window.RichRender = {
  splitFrontMatter,
  extractMath,
  markdownToHtml,
  applyStoredTheme,
  effectiveTheme,
  toggleTheme,
  initMermaid,
  runMermaid,
  buildToc,
  trackToc,
  toast,
  relativeTime,
  escapeHtml,
};
