import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { reportError } from "./telemetry";

describe("reportError", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  // The console sink is called with the message string first, then the structured report object.
  const lastReport = () => {
    const spy = console.error as unknown as ReturnType<typeof vi.fn>;
    return spy.mock.calls.at(-1)?.[1] as Record<string, unknown> | undefined;
  };

  it("reports an Error with its message and stack", () => {
    reportError(new Error("boom"));
    const report = lastReport();
    expect(report?.message).toBe("boom");
    expect(report?.stack).toBeTypeOf("string");
  });

  it("defaults the source to 'react'", () => {
    reportError(new Error("boom"));
    expect(lastReport()?.source).toBe("react");
  });

  it("carries the given source and component stack", () => {
    reportError(new Error("boom"), { source: "window", componentStack: "  at <Foo>" });
    const report = lastReport();
    expect(report?.source).toBe("window");
    expect(report?.componentStack).toBe("  at <Foo>");
  });

  it("normalizes a thrown string into a message", () => {
    reportError("just a string", { source: "unhandledrejection" });
    const report = lastReport();
    expect(report?.message).toBe("just a string");
    expect(report?.source).toBe("unhandledrejection");
  });

  it("normalizes a thrown non-Error value", () => {
    reportError({ code: 42 });
    expect(lastReport()?.message).toBe(JSON.stringify({ code: 42 }));
  });

  it("captures the current url, user agent, and an ISO timestamp", () => {
    reportError(new Error("boom"));
    const report = lastReport();
    expect(report?.url).toBe(window.location.href);
    expect(report?.userAgent).toBe(navigator.userAgent);
    expect(report?.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it("never throws, even on a value that cannot be stringified", () => {
    const circular: Record<string, unknown> = {};
    circular.self = circular; // JSON.stringify throws on this
    expect(() => reportError(circular)).not.toThrow();
  });
});
