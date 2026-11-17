import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getEnvelope } from "./client";

function respondWith(status: number, body: unknown, contentType = "application/json") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(typeof body === "string" ? body : JSON.stringify(body), {
        status,
        headers: { "Content-Type": contentType },
      }),
    ),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("getEnvelope", () => {
  it("returns the envelope and calls the versioned API path", async () => {
    respondWith(200, { data: { ok: true }, meta: { notes: [] } });

    const envelope = await getEnvelope<{ ok: boolean }>("/overview");

    expect(envelope.data).toEqual({ ok: true });
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe("/api/v1/overview");
  });

  it("keeps a null data field as null", async () => {
    respondWith(200, { data: null, meta: { notes: ["vehicle_positions: withheld"] } });

    const envelope = await getEnvelope<unknown[]>("/vehicles");

    expect(envelope.data).toBeNull();
    expect(envelope.meta.notes).toEqual(["vehicle_positions: withheld"]);
  });

  it("turns the API's error body into an ApiError", async () => {
    respondWith(404, { error: { code: "not_found", message: "No route 'R404' in the current schedule." } });

    const error = await getEnvelope("/routes/R404").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: "not_found" });
    expect((error as ApiError).isStarting).toBe(false);
  });

  it("treats 'not ready' answers as the server starting up", async () => {
    respondWith(503, { error: { code: "schedule_not_loaded", message: "Loading." } });

    const error = (await getEnvelope("/vehicles").catch((e: unknown) => e)) as ApiError;

    expect(error.isStarting).toBe(true);
  });

  it("survives a proxy's HTML error page", async () => {
    respondWith(502, "<html>Bad gateway</html>", "text/html");

    const error = (await getEnvelope("/status").catch((e: unknown) => e)) as ApiError;

    expect(error).toMatchObject({ status: 502, code: "http_error" });
    expect(error.isStarting).toBe(true);
  });

  it("reports an unreachable server as starting, not as a crash", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));

    const error = (await getEnvelope("/status").catch((e: unknown) => e)) as ApiError;

    expect(error).toMatchObject({ status: 0, code: "network" });
    expect(error.isStarting).toBe(true);
  });
});
