import katex from "katex";
import { Fragment, useMemo } from "react";

// Render engine prose that may contain LaTeX. Models are inconsistent: some wrap math in delimiters
// (we accept all four common styles — display `$$…$$` / `\[…\]`, inline `$…$` / `\(…\)`), and some
// emit bare macros with no delimiters at all (e.g. "a prior p(\theta)"). We typeset both: first the
// delimited spans, then any remaining `\macro` tokens in the prose. Anything KaTeX can't parse
// degrades to its plain source text rather than throwing or showing a red error box. KaTeX's CSS +
// fonts are loaded once in main.tsx.

// Display delimiters before the inline ones so an inline rule never splits a display block; all
// non-greedy. Inline `$…$` is held to a single line so an unbalanced `$` can't eat a paragraph.
const MATH_RE = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\$[^$\n]+?\$|\\\([\s\S]+?\\\))/g;

// A bare LaTeX macro the engine sometimes emits without delimiters: a command, any brace arguments,
// and an optional single sub/superscript — e.g. `\theta`, `\hat{R}`, `\sigma^2`, `\mathcal{N}`.
const MACRO_RE = /\\[a-zA-Z]+(?:\{[^{}]*\})*(?:[_^](?:\{[^{}]*\}|[A-Za-z0-9]+))?/g;

type Segment = { kind: "text"; value: string } | { kind: "math"; html: string };

// Peel the delimiters off a matched token → its TeX body + whether it is display math.
function classify(tok: string): { tex: string; display: boolean } {
  if (tok.startsWith("$$")) return { tex: tok.slice(2, -2), display: true };
  if (tok.startsWith("\\[")) return { tex: tok.slice(2, -2), display: true };
  if (tok.startsWith("\\(")) return { tex: tok.slice(2, -2), display: false };
  return { tex: tok.slice(1, -1), display: false }; // $…$
}

// Typeset one TeX string, or null if KaTeX can't parse it (caller falls back to source text).
function render(tex: string, display: boolean): string | null {
  try {
    return katex.renderToString(tex, {
      displayMode: display,
      throwOnError: true, // we catch and fall back to source text, never a red error box
      strict: "ignore", // be lenient (e.g. unicode inside text) instead of failing outright
      output: "html",
    });
  } catch {
    return null;
  }
}

// Scan a plain-prose run for bare `\macro` tokens and typeset each; the rest stays text.
function pushProse(out: Segment[], value: string): void {
  let last = 0;
  for (const m of value.matchAll(MACRO_RE)) {
    const start = m.index ?? 0;
    if (start > last) out.push({ kind: "text", value: value.slice(last, start) });
    const html = render(m[0], false);
    out.push(html ? { kind: "math", html } : { kind: "text", value: m[0] });
    last = start + m[0].length;
  }
  if (last < value.length) out.push({ kind: "text", value: value.slice(last) });
}

function parse(input: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  for (const m of input.matchAll(MATH_RE)) {
    const start = m.index ?? 0;
    if (start > last) pushProse(out, input.slice(last, start)); // prose between math → scan for macros
    const tok = m[0];
    const { tex, display } = classify(tok);
    const html = render(tex, display);
    if (html) out.push({ kind: "math", html });
    else pushProse(out, tok); // malformed delimited math → salvage any bare macros, else keep text
    last = start + tok.length;
  }
  if (last < input.length) pushProse(out, input.slice(last));
  return out;
}

export function MathText({ children }: { children: string }) {
  const segments = useMemo(() => parse(children ?? ""), [children]);
  return (
    <>
      {segments.map((s, i) =>
        s.kind === "text" ? (
          <Fragment key={i}>{s.value}</Fragment>
        ) : (
          <span
            key={i}
            // KaTeX returns sanitized HTML; trusted, deterministic markup from a fixed renderer.
            dangerouslySetInnerHTML={{ __html: s.html }}
          />
        ),
      )}
    </>
  );
}
