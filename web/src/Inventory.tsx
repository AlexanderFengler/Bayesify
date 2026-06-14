import type { EvidenceInventory, InventoryFamily, InventoryHit, PaperState } from "./types";

const FAMILY_NAMES: Record<string, string> = {
  software: "Software & tooling",
  method: "Bayesian methods",
  diagnostic: "Diagnostics",
  workflow: "Workflow signals",
  sampler: "Sampler configuration",
  open_science: "Open science",
};

// A friendlier label for a detector id (e.g. "software.stan" -> "stan").
function shortId(id: string): string {
  const dot = id.indexOf(".");
  return dot === -1 ? id : id.slice(dot + 1);
}

function valueText(value: Record<string, unknown> | null): string | null {
  if (!value) return null;
  const metric = value.metric as string | undefined;
  if (value.op != null && value.value != null) return `${metric} ${value.op} ${value.value}`;
  if (value.count != null) return `${metric}: ${value.count}`;
  return Object.entries(value)
    .map(([k, v]) => `${k}=${v}`)
    .join(", ");
}

export function Inventory({ paper, onReset }: { paper: PaperState; onReset: () => void }) {
  const inv = paper.inventory!;
  const families = inv.families.filter((f) => f.found.length > 0 || f.not_detected.length > 0);
  return (
    <div className="report inventory">
      <div className="report-head">
        <div>
          <div className="local-badge">Local-only · detection mode</div>
          <h1 className="report-title">{paper.source_label}</h1>
        </div>
        <button className="btn" onClick={onReset}>
          Analyze another
        </button>
      </div>

      <InventorySummary inv={inv} parser={paper.parser} paperId={paper.paper_id} />

      <p className="inventory-disclaimer">
        This is a <strong>detection inventory</strong>, not a graded assessment. Detectors find
        signals and show exactly where; they don&rsquo;t judge whether a practice was done{" "}
        <em>well</em> — that&rsquo;s the full (LLM) report&rsquo;s job. Absences mean{" "}
        <em>not detected</em>, never &ldquo;not done.&rdquo;
      </p>

      <div className="families">
        {families.map((f) => (
          <FamilyCard key={f.family} f={f} />
        ))}
      </div>

      <WhereLooked inv={inv} />
    </div>
  );
}

function InventorySummary({
  inv,
  parser,
  paperId,
}: {
  inv: EvidenceInventory;
  parser: string | null;
  paperId: string;
}) {
  return (
    <div className="summary inventory-summary">
      <div className="metric metric-primary">
        <div className="metric-value">{inv.n_hits}</div>
        <div className="metric-label">signals detected</div>
      </div>
      <div className="inventory-meta">
        <div>
          parsed with <strong>{parser ?? "—"}</strong> · {inv.where_looked.length} sections scanned
        </div>
        <div className="inventory-privacy">No LLM · nothing left this machine.</div>
        <div className="inventory-downloads">
          <a href={`/api/papers/${paperId}/report.json`} target="_blank" rel="noreferrer">
            report.json
          </a>
          <a href={`/api/papers/${paperId}/report.md`} target="_blank" rel="noreferrer">
            report.md
          </a>
        </div>
      </div>
    </div>
  );
}

function FamilyCard({ f }: { f: InventoryFamily }) {
  return (
    <section className="family-card">
      <header className="family-head">
        <h2 className="family-name">{FAMILY_NAMES[f.family] ?? f.family}</h2>
        <span className="family-count">{f.found.length} found</span>
      </header>

      {f.found.length > 0 ? (
        <ul className="hit-list">
          {f.found.map((h, i) => (
            <Hit key={i} h={h} />
          ))}
        </ul>
      ) : (
        <p className="family-empty">Nothing in this family detected.</p>
      )}

      {f.not_detected.length > 0 && (
        <div className="not-detected">
          <span className="nd-label">not detected</span>
          {f.not_detected.map((id) => (
            <span key={id} className="nd-chip">
              {shortId(id)}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function Hit({ h }: { h: InventoryHit }) {
  const v = valueText(h.value);
  return (
    <li className="hit">
      <div className="hit-head">
        <span className="hit-id">{shortId(h.detector_id)}</span>
        {v && <span className="hit-value">{v}</span>}
      </div>
      <blockquote className="evidence">
        &ldquo;{h.quote}&rdquo;
        <cite>
          {h.section_title || h.section_id}
          {h.page != null && `, p.${h.page}`}
        </cite>
      </blockquote>
    </li>
  );
}

function WhereLooked({ inv }: { inv: EvidenceInventory }) {
  return (
    <div className="where-looked">
      <div className="grounding-label">Where the engine looked</div>
      <div className="scanned">
        {inv.where_looked.map((s) => (
          <span key={s.section_id} className="scanned-chip" title={`${s.kind} · ${s.section_id}`}>
            {s.title || s.kind}
          </span>
        ))}
      </div>
      {inv.skipped.length > 0 && (
        <p className="skipped-note">
          Not scanned (a precision trap — reference lists name tools the paper doesn&rsquo;t use):{" "}
          {inv.skipped.map((s) => s.title || s.kind).join(", ")}.
        </p>
      )}
    </div>
  );
}
