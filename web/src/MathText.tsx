import katex from "katex";
import { Fragment, useMemo } from "react";

// Render engine prose that may contain LaTeX. The assessment prompts wrap math in `$…$` (inline) and
// `$$…$$` (display); everything else is plain text. We split on those delimiters and typeset only the
// math segments via KaTeX, leaving prose untouched — so a stray `$` (or malformed TeX) degrades to
// text rather than throwing (throwOnError: false). Drops straight into a <Typography> as inline flow.

// $$…$$ (display) first so the inline rule never splits a display block; both are non-greedy.
const MATH_RE = /(\$\$[^$]+?\$\$|\$[^$\n]+?\$)/g;

type Segment = { kind: "text"; value: string } | { kind: "math"; tex: string; display: boolean };

function parse(input: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  for (const m of input.matchAll(MATH_RE)) {
    const start = m.index ?? 0;
    if (start > last) out.push({ kind: "text", value: input.slice(last, start) });
    const tok = m[0];
    const display = tok.startsWith("$$");
    out.push({ kind: "math", tex: tok.slice(display ? 2 : 1, display ? -2 : -1), display });
    last = start + tok.length;
  }
  if (last < input.length) out.push({ kind: "text", value: input.slice(last) });
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
            dangerouslySetInnerHTML={{
              __html: katex.renderToString(s.tex, {
                displayMode: s.display,
                throwOnError: false,
                output: "html",
              }),
            }}
          />
        ),
      )}
    </>
  );
}
