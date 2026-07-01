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

// The article's own URL, but only when the user actually supplied one — a pasted http(s) link (the
// source label is the raw submission). Bare arXiv/DOI/OpenAlex ids and uploaded filenames return
// null. Used to make a paper title clickable without otherwise changing its appearance.
export function articleUrl(source: string | null | undefined): string | null {
  const s = source?.trim();
  return s && /^https?:\/\//i.test(s) ? s : null;
}
