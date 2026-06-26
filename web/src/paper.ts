// Display helpers for a paper's extracted metadata (title/authors/year). Best-effort: any field may
// be missing (PDF metadata is often sparse), so callers fall back to the title, then the filename.

// "Smith, Doe, Lee, et al. · 2021" — up to three authors, then "et al.", with the year appended.
// Returns null when there is neither an author nor a year to show.
export function formatByline(authors: string[], year: number | null): string | null {
  const shown = authors.slice(0, 3).join(", ");
  const people = authors.length > 3 ? `${shown}, et al.` : shown;
  const parts = [people, year ? String(year) : ""].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}
