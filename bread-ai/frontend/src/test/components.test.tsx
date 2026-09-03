import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ChatMessage from "../components/ChatMessage";
import Markdown from "../components/Markdown";
import Sources from "../components/Sources";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import type { Citation } from "../api/types";

const CITATION: Citation = {
  document_id: "d1",
  document_name: "BreadPlugin.java",
  chunk_id: "c1",
  chunk_index: 2,
  score: 0.8123,
  excerpt: "public void onEnable() { getLogger().info(\"ready\"); }",
  start_line: 10,
  end_line: 18,
};

describe("Markdown", () => {
  it("renders a fenced code block with a copy button", async () => {
    render(<Markdown content={"Here is code:\n\n```python\nprint('hi')\n```\n"} />);

    expect(screen.getByText("python")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /copy code/i })).toBeInTheDocument();
  });

  it("copies the block contents to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<Markdown content={"```ts\nconst a = 1;\n```"} />);
    await userEvent.click(screen.getByRole("button", { name: /copy code/i }));

    expect(writeText).toHaveBeenCalled();
    expect(String(writeText.mock.calls[0][0])).toContain("const a = 1;");
  });

  it("does not render raw HTML from model output", () => {
    const { container } = render(<Markdown content={'<img src="x" onerror="alert(1)">'} />);
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("Sources", () => {
  it("stays collapsed until asked, then shows the citation", async () => {
    render(<Sources sources={[CITATION]} />);

    expect(screen.getByText(/1 source from your documents/i)).toBeInTheDocument();
    expect(screen.queryByText("BreadPlugin.java")).toBeNull();

    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByText("BreadPlugin.java")).toBeInTheDocument();
    expect(screen.getByText(/lines 10–18/)).toBeInTheDocument();
  });

  it("renders nothing when there are no sources", () => {
    const { container } = render(<Sources sources={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ChatMessage", () => {
  it("shows an assistant answer with its model and citations", async () => {
    render(
      <ChatMessage
        message={{
          id: "m1",
          conversation_id: "c1",
          role: "assistant",
          content: "The plugin registers a command in `onEnable`.",
          sources: [CITATION],
          model_id: "Qwen/Qwen2.5-Coder-7B-Instruct",
          latency_ms: 1420,
          stopped_early: false,
          created_at: new Date().toISOString(),
        }}
      />,
    );

    expect(screen.getByText("Bread")).toBeInTheDocument();
    expect(screen.getByText(/Qwen2.5-Coder-7B-Instruct/)).toBeInTheDocument();
    expect(screen.getByText(/1.4 s/)).toBeInTheDocument();
    expect(screen.getByText(/1 source/)).toBeInTheDocument();
  });

  it("marks an answer that was stopped early", () => {
    render(
      <ChatMessage
        message={{
          id: "m2",
          conversation_id: "c1",
          role: "assistant",
          content: "Partial",
          sources: [],
          stopped_early: true,
          created_at: new Date().toISOString(),
        }}
      />,
    );
    expect(screen.getByText(/stopped early/)).toBeInTheDocument();
  });

  it("shows an error banner when generation failed", () => {
    render(
      <ChatMessage
        message={{
          id: "m3",
          conversation_id: "c1",
          role: "assistant",
          content: "",
          sources: [],
          stopped_early: false,
          error: "CUDA out of memory",
          created_at: new Date().toISOString(),
        }}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("CUDA out of memory");
  });
});

describe("States", () => {
  it("announces loading to assistive technology", () => {
    render(<LoadingState label="Loading models" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading models");
  });

  it("shows the empty state title and description", () => {
    render(<EmptyState title="No documents" description="Upload one to get started." />);
    expect(screen.getByText("No documents")).toBeInTheDocument();
    expect(screen.getByText("Upload one to get started.")).toBeInTheDocument();
  });

  it("shows the server hint alongside the error message", () => {
    render(
      <ErrorState
        error={Object.assign(new Error("Weights are not cached."), {
          name: "ApiError",
        })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Weights are not cached.");
  });
});
