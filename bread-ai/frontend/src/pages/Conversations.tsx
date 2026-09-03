/** A table view of every conversation, including archived ones. */

import { Archive, ArchiveRestore, MessageSquare, Pin, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useConversations, useDeleteConversation, useUpdateConversation } from "../api/hooks";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { formatRelativeTime } from "../lib/format";

export default function Conversations() {
  const [search, setSearch] = useState("");
  const conversations = useConversations(search);
  const update = useUpdateConversation();
  const remove = useDeleteConversation();

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <header className="mb-5">
        <h1 className="text-lg font-semibold text-ink-100">Conversations</h1>
        <p className="mt-1 text-sm text-ink-400">
          Every chat is stored in the SQLite file under your data directory. Deleting one here
          deletes its messages too.
        </p>
      </header>

      <div className="relative mb-4 max-w-sm">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink-500" aria-hidden />
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search by title"
          aria-label="Search conversations"
          className="field pl-8"
        />
      </div>

      {conversations.isLoading && <LoadingState label="Loading conversations" />}
      {conversations.isError && (
        <ErrorState error={conversations.error} onRetry={() => void conversations.refetch()} />
      )}

      {conversations.data?.length === 0 && (
        <EmptyState
          icon={<MessageSquare className="h-7 w-7" />}
          title={search ? "Nothing matches that search" : "No conversations yet"}
          description={
            search
              ? "Try a shorter search term."
              : "Start one from the Chat page. Bread names it after your first message."
          }
          action={
            <Link to="/" className="btn-primary">
              Go to chat
            </Link>
          }
        />
      )}

      {conversations.data && conversations.data.length > 0 && (
        <div className="panel overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-ink-800 text-left text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-4 py-2 font-medium">Title</th>
                <th className="hidden px-4 py-2 font-medium sm:table-cell">Messages</th>
                <th className="hidden px-4 py-2 font-medium md:table-cell">Updated</th>
                <th className="px-4 py-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {conversations.data.map((conversation) => (
                <tr key={conversation.id} className="hover:bg-ink-800/40">
                  <td className="px-4 py-2">
                    <Link
                      to={`/chat/${conversation.id}`}
                      className="font-medium text-ink-100 hover:text-crust-200"
                    >
                      {conversation.title}
                    </Link>
                    {conversation.last_message_preview && (
                      <p className="mt-0.5 truncate text-xs text-ink-500">
                        {conversation.last_message_preview}
                      </p>
                    )}
                  </td>
                  <td className="hidden px-4 py-2 text-ink-300 sm:table-cell">
                    {conversation.message_count}
                  </td>
                  <td className="hidden px-4 py-2 text-ink-400 md:table-cell">
                    {formatRelativeTime(conversation.updated_at)}
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        type="button"
                        aria-label={conversation.pinned ? "Unpin" : "Pin"}
                        title={conversation.pinned ? "Unpin" : "Pin"}
                        onClick={() =>
                          update.mutate({
                            id: conversation.id,
                            body: { pinned: !conversation.pinned },
                          })
                        }
                        className={`rounded p-1.5 hover:bg-ink-800 ${
                          conversation.pinned ? "text-crust-300" : "text-ink-500"
                        }`}
                      >
                        <Pin className="h-4 w-4" aria-hidden />
                      </button>
                      <button
                        type="button"
                        aria-label={conversation.archived ? "Unarchive" : "Archive"}
                        title={conversation.archived ? "Unarchive" : "Archive"}
                        onClick={() =>
                          update.mutate({
                            id: conversation.id,
                            body: { archived: !conversation.archived },
                          })
                        }
                        className="rounded p-1.5 text-ink-500 hover:bg-ink-800 hover:text-ink-200"
                      >
                        {conversation.archived ? (
                          <ArchiveRestore className="h-4 w-4" aria-hidden />
                        ) : (
                          <Archive className="h-4 w-4" aria-hidden />
                        )}
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete ${conversation.title}`}
                        onClick={() => remove.mutate(conversation.id)}
                        className="rounded p-1.5 text-ink-500 hover:bg-ink-800 hover:text-red-300"
                      >
                        <Trash2 className="h-4 w-4" aria-hidden />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
