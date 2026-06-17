import type { Rubric } from "./rubric";

// The rubric explanation shown at the top of the report and under the landing-page picker. It names
// every step explicitly so the "S1, S2, …" labels in the at-a-glance strip have real names attached
// (otherwise readers see only the bare codes). `showHeader` adds the same small-caps section header
// the report uses for "Steps at a glance"; the landing page omits it (it already has a "Rubric" label).
export function RubricAbout({ rubric, showHeader = false }: { rubric: Rubric; showHeader?: boolean }) {
  return (
    <div className="rubric-about">
      {showHeader && <div className="grounding-label">About this rubric</div>}
      <p className="rubric-preamble">
        <strong>{rubric.label}.</strong> {rubric.summary}
      </p>
      {rubric.steps.length > 0 && (
        <ol className="rubric-steplist">
          {rubric.steps.map((s) => (
            <li key={s.id}>
              <span className="rubric-steplist-id">{s.id}</span>
              <span className="rubric-steplist-name">{s.name}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
