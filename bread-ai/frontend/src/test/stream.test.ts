/**
 * The SSE parser is the piece most likely to break silently, because a
 * mis-framed stream just looks like a slow model. These tests feed it chunks
 * split in awkward places on purpose.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { streamChat } from "../api/stream";

function mockStream(chunks: string[]): void {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(body, { status: 200 })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("streamChat", () => {
  it("parses meta, token and done events", async () => {
    mockStream([
      'event: meta\ndata: {"conversation_id":"c1","stream_id":"s1","model_id":"m","backend":"mock","sources":[]}\n\n',
      'event: token\ndata: {"delta":"Hello "}\n\n',
      'event: token\ndata: {"delta":"world"}\n\n',
      'event: done\ndata: {"conversation_id":"c1","message_id":"m1","latency_ms":12,"stopped_early":false,"characters":11,"error":null}\n\n',
    ]);

    const tokens: string[] = [];
    let conversationId = "";
    let messageId = "";

    await streamChat(
      { message: "hi" },
      {
        onMeta: (meta) => {
          conversationId = meta.conversation_id;
        },
        onToken: (delta) => tokens.push(delta),
        onDone: (done) => {
          messageId = done.message_id;
        },
      },
    );

    expect(conversationId).toBe("c1");
    expect(tokens.join("")).toBe("Hello world");
    expect(messageId).toBe("m1");
  });

  it("reassembles events split across network chunks", async () => {
    mockStream([
      'event: tok',
      'en\ndata: {"delta":"par',
      'tial"}\n',
      '\nevent: token\ndata: {"delta":"!"}\n\n',
    ]);

    const tokens: string[] = [];
    await streamChat({ message: "hi" }, { onToken: (delta) => tokens.push(delta) });
    expect(tokens.join("")).toBe("partial!");
  });

  it("surfaces an error event instead of failing silently", async () => {
    mockStream([
      'event: error\ndata: {"code":"generation_failed","message":"CUDA out of memory"}\n\n',
    ]);

    const errors: string[] = [];
    await streamChat({ message: "hi" }, { onError: (error) => errors.push(error.message) });
    expect(errors).toEqual(["CUDA out of memory"]);
  });

  it("ignores malformed frames rather than throwing", async () => {
    mockStream(['event: token\ndata: {not json}\n\n', 'event: token\ndata: {"delta":"ok"}\n\n']);

    const tokens: string[] = [];
    await streamChat({ message: "hi" }, { onToken: (delta) => tokens.push(delta) });
    expect(tokens).toEqual(["ok"]);
  });

  it("throws a structured error when the server refuses the request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "model_not_loaded", message: "No model is loaded." },
          }),
          { status: 409 },
        ),
      ),
    );

    await expect(streamChat({ message: "hi" }, {})).rejects.toMatchObject({
      code: "model_not_loaded",
      status: 409,
    });
  });
});
