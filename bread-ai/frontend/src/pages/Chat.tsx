/**
 * The chat page.
 *
 * Streaming state lives here rather than in the query cache: a partially
 * received answer is not server state, and treating it as such makes it fight
 * with refetches.
 */

import {
  Check,
  MessageSquarePlus,
  Paperclip,
  Pencil,
  Search,
  Send,
  Square,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { describeError } from "../api/client";
import {
  useConversation,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useKnowledgeSpaces,
  useModelStatus,
  useModels,
  usePresets,
  useRollbackMessage,
  useUpdateConversation,
  useUploadDocuments,
} from "../api/hooks";
import { stopStream, streamChat } from "../api/stream";
import type { ChatMessage as ChatMessageType, Citation } from "../api/types";
import ChatMessage from "../components/ChatMessage";
import { ErrorState, InlineNotice, LoadingState } from "../components/States";
import { formatRelativeTime, truncate } from "../lib/format";

interface DraftAnswer {
  content: string;
  sources: Citation[];
  modelId: string;
  streamId: string;
}

const SUGGESTIONS = [
  "Explain what this function does and name one edge case it misses.",
  "Write a Paper plugin command that teleports a player to spawn.",
  "This stack trace says NullPointerException at line 42. Where do I look first?",
  "Convert this Python class to TypeScript, keeping the same behaviour.",
];

export default function Chat() {
  const { conversationId } = useParams();
  const navigate = useNavigate();

  const [search, setSearch] = useState("");
  const [input, setInput] = useState("");
  const [draft, setDraft] = useState<DraftAnswer | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const [temperature, setTemperature] = useState(0.2);
  const [maxTokens, setMaxTokens] = useState(1024);
  const [ragEnabled, setRagEnabled] = useState(false);
  const [spaceId, setSpaceId] = useState<string>("");
  const [modelId, setModelId] = useState<string>("");
  const [preset, setPreset] = useState<string>("");

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const conversations = useConversations(search);
  const conversation = useConversation(conversationId);
  const spaces = useKnowledgeSpaces();
  const models = useModels();
  const modelStatus = useModelStatus();
  const presets = usePresets();

  const createConversation = useCreateConversation();
  const updateConversation = useUpdateConversation();
  const deleteConversation = useDeleteConversation();
  const rollback = useRollbackMessage();
  const upload = useUploadDocuments();

  const messages = conversation.data?.messages ?? [];
  const isStreaming = draft !== null;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, draft?.content]);

  // Abort any in-flight stream when the page unmounts, so a navigation away
  // does not leave a reader hanging on a body nobody is consuming.
  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(
    async (text: string, targetConversationId?: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      setStreamError(null);
      setInput("");
      const controller = new AbortController();
      abortRef.current = controller;
      setDraft({ content: "", sources: [], modelId: "", streamId: "" });

      try {
        await streamChat(
          {
            conversation_id: targetConversationId ?? conversationId,
            message: trimmed,
            temperature,
            max_new_tokens: maxTokens,
            rag_enabled: ragEnabled,
            knowledge_space_id: ragEnabled && spaceId ? spaceId : undefined,
            model_id: modelId || undefined,
            preset: preset || undefined,
          },
          {
            onMeta: (meta) => {
              setDraft((current) =>
                current
                  ? {
                      ...current,
                      sources: meta.sources,
                      modelId: meta.model_id,
                      streamId: meta.stream_id,
                    }
                  : current,
              );
              if (!conversationId) {
                navigate(`/chat/${meta.conversation_id}`, { replace: true });
              }
            },
            onToken: (delta) =>
              setDraft((current) =>
                current ? { ...current, content: current.content + delta } : current,
              ),
            onError: (error) => setStreamError(error.hint ? `${error.message} ${error.hint}` : error.message),
          },
          controller.signal,
        );
      } catch (error) {
        const { message, hint } = describeError(error);
        setStreamError(hint ? `${message} ${hint}` : message);
      } finally {
        abortRef.current = null;
        setDraft(null);
        void conversations.refetch();
        void conversation.refetch();
      }
    },
    [
      conversationId,
      conversation,
      conversations,
      isStreaming,
      maxTokens,
      modelId,
      navigate,
      preset,
      ragEnabled,
      spaceId,
      temperature,
    ],
  );

  const stop = useCallback(async () => {
    await stopStream(draft?.streamId, conversationId);
  }, [conversationId, draft?.streamId]);

  const regenerate = useCallback(
    async (assistantMessage: ChatMessageType) => {
      if (!conversationId) return;
      const index = messages.findIndex((message) => message.id === assistantMessage.id);
      const previousUserMessage = [...messages.slice(0, index)]
        .reverse()
        .find((message) => message.role === "user");
      if (!previousUserMessage) return;

      await rollback.mutateAsync({
        conversationId,
        messageId: previousUserMessage.id,
      });
      await send(previousUserMessage.content, conversationId);
    },
    [conversationId, messages, rollback, send],
  );

  const startNewChat = async () => {
    const created = await createConversation.mutateAsync({ title: "New chat" });
    navigate(`/chat/${created.id}`);
    inputRef.current?.focus();
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const result = await upload.mutateAsync({
      files: Array.from(files),
      spaceId: spaceId || undefined,
    });
    if (result.documents.length > 0) {
      setRagEnabled(true);
    }
    if (fileRef.current) fileRef.current.value = "";
  };

  const modelOptions = useMemo(() => models.data ?? [], [models.data]);

  return (
    <div className="flex h-full min-h-0">
      {/* ---------------------------------------------------------- sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-ink-800 bg-ink-900/50 lg:flex">
        <div className="space-y-2 p-3">
          <button type="button" className="btn-primary w-full" onClick={startNewChat}>
            <MessageSquarePlus className="h-4 w-4" aria-hidden />
            New chat
          </button>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink-500"
              aria-hidden
            />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search conversations"
              aria-label="Search conversations"
              className="field pl-8"
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {conversations.isLoading && <LoadingState label="Loading conversations" />}
          {conversations.isError && <ErrorState error={conversations.error} />}
          {conversations.data?.length === 0 && (
            <p className="px-2 py-6 text-center text-xs text-ink-500">
              {search ? "No conversation matches that search." : "No conversations yet."}
            </p>
          )}

          <ul className="space-y-0.5">
            {conversations.data?.map((item) => {
              const active = item.id === conversationId;
              return (
                <li key={item.id}>
                  {renamingId === item.id ? (
                    <form
                      className="flex items-center gap-1 px-1 py-1"
                      onSubmit={async (event) => {
                        event.preventDefault();
                        await updateConversation.mutateAsync({
                          id: item.id,
                          body: { title: renameValue.trim() || item.title },
                        });
                        setRenamingId(null);
                      }}
                    >
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(event) => setRenameValue(event.target.value)}
                        className="field py-1 text-xs"
                        aria-label="Conversation title"
                      />
                      <button type="submit" className="rounded p-1 text-emerald-400 hover:bg-ink-800">
                        <Check className="h-4 w-4" aria-hidden />
                      </button>
                    </form>
                  ) : (
                    <div
                      className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 ${
                        active ? "bg-ink-800" : "hover:bg-ink-800/60"
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => navigate(`/chat/${item.id}`)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <p
                          className={`truncate text-sm ${
                            active ? "text-crust-200" : "text-ink-200"
                          }`}
                        >
                          {item.title}
                        </p>
                        <p className="truncate text-[11px] text-ink-500">
                          {item.message_count} messages · {formatRelativeTime(item.updated_at)}
                        </p>
                      </button>
                      <button
                        type="button"
                        aria-label={`Rename ${item.title}`}
                        onClick={() => {
                          setRenamingId(item.id);
                          setRenameValue(item.title);
                        }}
                        className="rounded p-1 text-ink-500 opacity-0 hover:bg-ink-700
                          hover:text-ink-200 focus:opacity-100 group-hover:opacity-100"
                      >
                        <Pencil className="h-3.5 w-3.5" aria-hidden />
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete ${item.title}`}
                        onClick={async () => {
                          await deleteConversation.mutateAsync(item.id);
                          if (active) navigate("/");
                        }}
                        className="rounded p-1 text-ink-500 opacity-0 hover:bg-ink-700
                          hover:text-red-300 focus:opacity-100 group-hover:opacity-100"
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden />
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </aside>

      {/* ------------------------------------------------------- main panel */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
          {conversation.isLoading && conversationId && <LoadingState label="Loading conversation" />}
          {conversation.isError && <ErrorState error={conversation.error} />}

          {!conversationId && messages.length === 0 && !isStreaming && (
            <div className="mx-auto max-w-2xl px-6 py-16">
              <div className="text-center">
                <p className="text-5xl" aria-hidden>
                  🍞
                </p>
                <h1 className="mt-4 text-xl font-semibold text-ink-100">
                  Ask Bread something about your code
                </h1>
                <p className="mx-auto mt-2 max-w-md text-sm text-ink-400">
                  Bread runs an open-weight model on this machine. Nothing you type leaves it.
                </p>
              </div>

              {!modelStatus.data?.loaded && (
                <div className="mt-6">
                  <InlineNotice tone="warning">
                    No model is loaded. The mock backend answers with a fixed template so you can
                    try the interface; load a real model from the Models page for real answers.
                  </InlineNotice>
                </div>
              )}

              <ul className="mt-8 grid gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((suggestion) => (
                  <li key={suggestion}>
                    <button
                      type="button"
                      onClick={() => {
                        setInput(suggestion);
                        inputRef.current?.focus();
                      }}
                      className="panel h-full w-full p-3 text-left text-sm text-ink-300
                        transition-colors hover:border-crust-700 hover:text-ink-100"
                    >
                      {truncate(suggestion, 90)}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {messages.map((message) => (
            <ChatMessage
              key={message.id}
              message={message}
              onRegenerate={
                message.role === "assistant" ? () => void regenerate(message) : undefined
              }
            />
          ))}

          {draft && (
            <ChatMessage
              streaming
              message={{
                id: "streaming",
                conversation_id: conversationId ?? "",
                role: "assistant",
                content: draft.content || "…",
                sources: draft.sources,
                model_id: draft.modelId,
                stopped_early: false,
                created_at: new Date().toISOString(),
              }}
            />
          )}

          {streamError && (
            <div className="mx-auto max-w-3xl px-4 pb-4 sm:px-6">
              <ErrorState error={new Error(streamError)} />
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* ----------------------------------------------------- composer */}
        <div className="border-t border-ink-800 bg-ink-900/40 px-4 py-3 sm:px-6">
          <div className="mx-auto max-w-3xl space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <label className="flex items-center gap-1.5 text-ink-400">
                Model
                <select
                  value={modelId}
                  onChange={(event) => setModelId(event.target.value)}
                  className="rounded border border-ink-800 bg-ink-950 px-2 py-1 text-ink-200"
                  aria-label="Model"
                >
                  <option value="">Loaded model</option>
                  {modelOptions.map((model) => (
                    <option key={model.id} value={model.model_id}>
                      {model.name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex items-center gap-1.5 text-ink-400">
                Temperature
                <input
                  type="range"
                  min={0}
                  max={1.5}
                  step={0.05}
                  value={temperature}
                  onChange={(event) => setTemperature(Number(event.target.value))}
                  className="w-24 accent-crust-500"
                  aria-label="Temperature"
                />
                <span className="w-8 font-mono text-ink-300">{temperature.toFixed(2)}</span>
              </label>

              <label className="flex items-center gap-1.5 text-ink-400">
                Max tokens
                <input
                  type="number"
                  min={64}
                  max={32768}
                  step={64}
                  value={maxTokens}
                  onChange={(event) => setMaxTokens(Number(event.target.value))}
                  className="w-20 rounded border border-ink-800 bg-ink-950 px-2 py-1 text-ink-200"
                  aria-label="Maximum new tokens"
                />
              </label>

              <label className="flex items-center gap-1.5 text-ink-400">
                <input
                  type="checkbox"
                  checked={ragEnabled}
                  onChange={(event) => setRagEnabled(event.target.checked)}
                  className="accent-crust-500"
                />
                Use my documents
              </label>

              {ragEnabled && (
                <select
                  value={spaceId}
                  onChange={(event) => setSpaceId(event.target.value)}
                  className="rounded border border-ink-800 bg-ink-950 px-2 py-1 text-ink-200"
                  aria-label="Knowledge space"
                >
                  <option value="">First knowledge space</option>
                  {spaces.data?.map((space) => (
                    <option key={space.id} value={space.id}>
                      {space.name} ({space.chunk_count} chunks)
                    </option>
                  ))}
                </select>
              )}

              <select
                value={preset}
                onChange={(event) => setPreset(event.target.value)}
                className="rounded border border-ink-800 bg-ink-950 px-2 py-1 text-ink-200"
                aria-label="Prompt preset"
              >
                <option value="">No preset</option>
                {presets.data?.map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.title}
                  </option>
                ))}
              </select>
            </div>

            {upload.data && upload.data.skipped.length > 0 && (
              <InlineNotice tone="warning">
                {upload.data.skipped.map((item) => `${item.filename}: ${item.reason}`).join(" ")}
              </InlineNotice>
            )}

            <form
              className="flex items-end gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                void send(input);
              }}
            >
              <input
                ref={fileRef}
                type="file"
                multiple
                className="hidden"
                onChange={(event) => void handleUpload(event.target.files)}
              />
              <button
                type="button"
                className="btn-ghost h-[42px] px-3"
                onClick={() => fileRef.current?.click()}
                disabled={upload.isPending}
                aria-label="Upload files into a knowledge space"
                title="Upload files into a knowledge space"
              >
                <Paperclip className="h-4 w-4" aria-hidden />
              </button>

              <textarea
                ref={inputRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void send(input);
                  }
                }}
                rows={1}
                placeholder="Ask about your code. Shift+Enter for a new line."
                aria-label="Message"
                className="field max-h-48 min-h-[42px] flex-1 resize-y"
              />

              {isStreaming ? (
                <button type="button" className="btn-ghost h-[42px]" onClick={() => void stop()}>
                  <Square className="h-4 w-4" aria-hidden />
                  Stop
                </button>
              ) : (
                <button type="submit" className="btn-primary h-[42px]" disabled={!input.trim()}>
                  <Send className="h-4 w-4" aria-hidden />
                  Send
                </button>
              )}
            </form>

            <p className="text-[11px] text-ink-500">
              Bread runs locally and can be wrong. Check generated code before you run it; Bread
              never executes it for you.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
