import { describe, expect, it } from "vitest";
import { articleUrl, formatByline } from "./paper";

describe("formatByline", () => {
  it("returns null when there is neither an author nor a year", () => {
    expect(formatByline([], null)).toBeNull();
  });

  it("shows the year alone when there are no authors", () => {
    expect(formatByline([], 2021)).toBe("2021");
  });

  it("shows a single author with no year", () => {
    expect(formatByline(["Smith"], null)).toBe("Smith");
  });

  it("joins the author and year with a middot", () => {
    expect(formatByline(["Smith"], 2021)).toBe("Smith · 2021");
  });

  it("lists up to three authors in full", () => {
    expect(formatByline(["Smith", "Doe", "Lee"], 2021)).toBe("Smith, Doe, Lee · 2021");
  });

  it("collapses a fourth-and-beyond author into 'et al.'", () => {
    expect(formatByline(["Smith", "Doe", "Lee", "Ng"], 2021)).toBe("Smith, Doe, Lee, et al. · 2021");
  });

  it("keeps 'et al.' even without a year", () => {
    expect(formatByline(["A", "B", "C", "D"], null)).toBe("A, B, C, et al.");
  });
});

describe("articleUrl", () => {
  it.each([null, undefined, "", "   "])("returns null for the empty/absent source %j", (source) => {
    expect(articleUrl(source)).toBeNull();
  });

  it.each(["arXiv:2101.00001", "10.1234/xyz", "openalex:W123", "some_uploaded_file.pdf"])(
    "returns null for the non-URL identifier %j",
    (source) => {
      expect(articleUrl(source)).toBeNull();
    },
  );

  it("returns an http(s) link the user pasted", () => {
    expect(articleUrl("https://example.com/paper")).toBe("https://example.com/paper");
    expect(articleUrl("http://example.com/paper")).toBe("http://example.com/paper");
  });

  it("trims surrounding whitespace", () => {
    expect(articleUrl("  https://example.com  ")).toBe("https://example.com");
  });

  it("matches the scheme case-insensitively and preserves the original casing", () => {
    expect(articleUrl("HTTPS://Example.com")).toBe("HTTPS://Example.com");
  });

  it("rejects non-http schemes", () => {
    expect(articleUrl("ftp://example.com")).toBeNull();
    expect(articleUrl("javascript:alert(1)")).toBeNull();
  });
});
