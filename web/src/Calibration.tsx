import { useEffect, useState } from "react";
import { type CalibrationReport, getCalibration, type MetricStat } from "./api";

// The full calibration view: it renders the validation report the harness produced — honestly. The
// status drives a per-state banner; the demo state gets a loud, non-dismissable FAKE-DATA banner so
// fabricated numbers can never be mistaken for a real measurement.
export function Calibration({ onExit }: { onExit: () => void }) {
  const [rep, setRep] = useState<CalibrationReport | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    getCalibration()
      .then(setRep)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  if (err) {
    return (
      <div className="report">
        <div className="card error-card">
          <h2>Couldn&rsquo;t load calibration</h2>
          <p>{err}</p>
          <button className="btn" onClick={onExit}>
            Back
          </button>
        </div>
      </div>
    );
  }
  if (!rep) return <div className="card">Loading…</div>;

  return (
    <div className="report calibration">
      <div className="report-head">
        <div>
          <div className="report-eyebrow">Calibration</div>
          <h1 className="report-title">Engine vs. expert agreement</h1>
        </div>
        <button className="btn" onClick={onExit}>
          Back
        </button>
      </div>

      <StatusBanner rep={rep} />

      {rep.status === "not_yet_validated" ? (
        <div className="card na-card">
          <p className="na-lead">
            {rep.note ??
              "No validation has run yet. Coverage and quality scores are produced, but they have " +
                "not been checked against expert ratings."}
          </p>
          <p className="na-foot">
            Until the validation run (M7) reports agreement metrics, treat every report as{" "}
            <strong>formative, not a verdict</strong>.
          </p>
        </div>
      ) : (
        <>
          <MetaLine rep={rep} />
          <Metrics rep={rep} />
          {rep.confusion && <Confusion table={rep.confusion} />}
          <Caveats caveats={rep.validity_caveats ?? []} />
        </>
      )}
    </div>
  );
}

function StatusBanner({ rep }: { rep: CalibrationReport }) {
  if (rep.status === "demo_fake_data") {
    return (
      <div className="calib-banner calib-demo">
        <strong>⚠️ FAKE DATA — plumbing demonstration, not a measurement.</strong> Every number below
        is computed from fabricated reports so the page can be built and critiqued before real expert
        ratings exist. It is <strong>not</strong> the engine&rsquo;s accuracy.
      </div>
    );
  }
  if (rep.status === "development_set") {
    return (
      <div className="calib-banner calib-dev">
        <strong>Development-set agreement.</strong> Measured against the gold set the engine is tuned
        on — not held-out accuracy. Every number is labelled &ldquo;development-set agreement.&rdquo;
      </div>
    );
  }
  if (rep.status === "holdout") {
    return (
      <div className="calib-banner calib-holdout">
        <strong>Held-out accuracy.</strong> Measured on a sealed holdout the engine never saw.
      </div>
    );
  }
  return (
    <div className="calib-banner calib-pending">
      <strong>Not yet validated.</strong>
    </div>
  );
}

function MetaLine({ rep }: { rep: CalibrationReport }) {
  const raters = Object.entries(rep.rater_relationships ?? {})
    .map(([k, v]) => `${v} ${k}`)
    .join(", ");
  return (
    <div className="calib-meta">
      <div>
        <strong>{rep.n_papers ?? 0}</strong> papers
        {rep.n_excluded ? ` (${rep.n_excluded} excluded)` : ""} ·{" "}
        {Object.entries(rep.tier_counts ?? {})
          .map(([t, n]) => `tier ${t}: ${n}`)
          .join(", ")}
      </div>
      <div className="calib-meta-sub">
        engine {rep.engine_version} · rubric {rep.rubric_version} · {rep.rubric_profile} profile
        {raters && ` · raters: ${raters}`}
      </div>
      {rep.domain_note && <div className="calib-domain">{rep.domain_note}</div>}
    </div>
  );
}

function fmt(s: MetricStat): string {
  if (s.value === null || s.value === undefined) return "—";
  let body = s.value.toFixed(2);
  if (s.x !== undefined) body += ` (${s.x}/${s.n})`;
  if (s.ci_lo !== null && s.ci_hi !== null) body += ` [${s.ci_lo.toFixed(2)}, ${s.ci_hi.toFixed(2)}]`;
  return body;
}

function Metric({ s }: { s?: MetricStat }) {
  if (!s) return null;
  return (
    <div className={"calib-metric" + (s.preliminary ? " calib-prelim" : "")}>
      <span className="calib-metric-label">{s.label}</span>
      <span className="calib-metric-value">
        {fmt(s)}
        {s.preliminary && s.value !== null && (
          <span className="calib-prelim-tag" title="n below the minimum-data floor">
            preliminary
          </span>
        )}
      </span>
    </div>
  );
}

function Metrics({ rep }: { rep: CalibrationReport }) {
  const order: (MetricStat | undefined)[] = [
    rep.applicability_kappa,
    rep.status_kappa,
    rep.status_percent_agreement,
    rep.status_ac1,
    rep.inter_expert_status_kappa,
    rep.absence_fpr_strict,
    rep.absence_fpr_broad,
    rep.absence_miss_rate,
    rep.coverage_icc,
    rep.quality_icc,
    rep.relevance_sensitivity,
    rep.relevance_specificity,
    rep.paper_class_accuracy,
  ];
  return (
    <div className="calib-metrics">
      <div className="grounding-label">Agreement metrics</div>
      {order.map((s, i) => (
        <Metric key={i} s={s} />
      ))}
    </div>
  );
}

function Confusion({ table }: { table: Record<string, Record<string, number>> }) {
  const rows = Object.keys(table);
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(table[r]))));
  return (
    <div className="calib-confusion">
      <div className="grounding-label">Status confusion (rows = consensus, cols = engine)</div>
      <table>
        <thead>
          <tr>
            <th />
            {cols.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r}>
              <th>{r}</th>
              {cols.map((c) => (
                <td key={c}>{table[r][c] ?? 0}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Caveats({ caveats }: { caveats: string[] }) {
  if (caveats.length === 0) return null;
  return (
    <div className="calib-caveats">
      <div className="grounding-label">Read this carefully</div>
      <ul>
        {caveats.map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ul>
    </div>
  );
}
