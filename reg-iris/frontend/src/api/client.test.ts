import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, request, toQueryString } from "./client";

describe("toQueryString", () => {
  it("repeats array keys and drops empty values", () => {
    expect(toQueryString({ q: "LEI", regulator: ["EMIR", "FCA"], status: undefined, page: 1, x: "" })).toBe(
      "?q=LEI&regulator=EMIR&regulator=FCA&page=1",
    );
  });
  it("returns an empty string when nothing is set", () => {
    expect(toQueryString({})).toBe("");
  });
});

describe("request", () => {
  afterEach(() => vi.restoreAllMocks());

  it("turns the backend error envelope into an ApiError", async () => {
    const body = { error: { code: "DUPLICATE_DOCUMENT", message: "Already uploaded", details: { version_id: "v1" }, request_id: "r1" } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 409 })));
    const err = await request("/api/v1/documents").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 409, code: "DUPLICATE_DOCUMENT", requestId: "r1" });
  });
});
