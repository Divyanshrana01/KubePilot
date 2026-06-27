import { useCallback, useMemo, useState } from "react";
import { Boxes, LogOut } from "lucide-react";
import { api, ApiError, queryStream } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import {
  DEFAULT_FLAGS,
  type AssistantMessage,
  type ChatMessage,
  type QueryFlags,
} from "@/chat/types";
import { Button } from "@/components/ui/button";
import { Composer } from "./Composer";
import { MessageList } from "./MessageList";
import { TracePanel } from "./TracePanel";

function newId() {
  return crypto.randomUUID();
}

export function Chat() {
  const { logout } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [flags, setFlags] = useState<QueryFlags>(DEFAULT_FLAGS);
  const [busy, setBusy] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);

  // Replace a single assistant message in place (used when a request resolves).
  const patchMessage = useCallback((id: string, patch: Partial<AssistantMessage>) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id && m.role === "assistant" ? { ...m, ...patch } : m)),
    );
  }, []);

  // Append a streamed token to an assistant message's running text.
  const appendToken = useCallback((id: string, text: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id && m.role === "assistant"
          ? { ...m, streamedText: (m.streamedText ?? "") + text }
          : m,
      ),
    );
  }, []);

  const handleAuthError = useCallback(
    (err: unknown): string => {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          logout();
          return "Your session expired. Please sign in again.";
        }
        return err.message;
      }
      return "Network error — is the API running?";
    },
    [logout],
  );

  const runQuery = useCallback(
    async (question: string, flagsToUse: QueryFlags) => {
      if (!question || busy) return;

      const userMsg: ChatMessage = { id: newId(), role: "user", text: question };
      const assistantId = newId();
      const assistantMsg: AssistantMessage = {
        id: assistantId,
        role: "assistant",
        question,
        flags: flagsToUse,
        response: null,
        stage: "routing",
        streamedText: "",
      };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setBusy(true);

      try {
        await queryStream(
          { question, ...flagsToUse },
          {
            onStage: (stage) => patchMessage(assistantId, { stage }),
            onToken: (text) => appendToken(assistantId, text),
            onDone: (response) => {
              patchMessage(assistantId, { response, stage: null });
              if (!response.pending_sql) setActiveId(assistantId);
            },
            onError: (err) =>
              patchMessage(assistantId, { error: handleAuthError(err), stage: null }),
          },
        );
      } catch (err) {
        patchMessage(assistantId, { error: handleAuthError(err), stage: null });
      } finally {
        setBusy(false);
      }
    },
    [busy, patchMessage, appendToken, handleAuthError],
  );

  const send = useCallback(() => {
    const question = input.trim();
    if (!question || busy) return;
    setInput("");
    void runQuery(question, flags);
  }, [input, busy, flags, runQuery]);

  // Re-run a question with adjusted pipeline flags (from the "improve this answer"
  // nudge), and reflect the new flags in the composer toggles.
  const retry = useCallback(
    (question: string, newFlags: QueryFlags) => {
      setFlags(newFlags);
      void runQuery(question, newFlags);
    },
    [runQuery],
  );

  // Resume the paused graph run after the user approves/rejects the generated SQL.
  const approveSql = useCallback(
    async (queryId: string, approved: boolean) => {
      // Find the assistant message currently showing this pending SQL block.
      const target = messages.find(
        (m): m is AssistantMessage =>
          m.role === "assistant" && m.response?.pending_sql?.query_id === queryId,
      );
      try {
        const response = await api.approveSql({ query_id: queryId, approved });
        if (target) {
          patchMessage(target.id, { response });
          if (!response.pending_sql) setActiveId(target.id);
        }
      } catch (err) {
        if (target) patchMessage(target.id, { error: handleAuthError(err) });
      }
    },
    [messages, patchMessage, handleAuthError],
  );

  const activeResponse = useMemo(() => {
    const active = messages.find(
      (m): m is AssistantMessage => m.id === activeId && m.role === "assistant",
    );
    return active?.response ?? null;
  }, [messages, activeId]);

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/15">
            <Boxes className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h1 className="text-sm font-semibold leading-none">KubePilot</h1>
            <p className="text-xs text-muted-foreground">Kubernetes SRE Copilot</p>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={logout}>
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </header>

      <div className="flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex-1 overflow-y-auto p-4">
            <div className="mx-auto h-full max-w-3xl">
              <MessageList
                messages={messages}
                activeId={activeId}
                busy={busy}
                onSelect={setActiveId}
                onApproveSql={approveSql}
                onRetry={retry}
              />
            </div>
          </div>
          <div className="mx-auto w-full max-w-3xl">
            <Composer
              value={input}
              onChange={setInput}
              onSend={send}
              busy={busy}
              flags={flags}
              onFlagsChange={setFlags}
            />
          </div>
        </main>

        <aside className="hidden w-80 shrink-0 border-l lg:block">
          <TracePanel response={activeResponse} />
        </aside>
      </div>
    </div>
  );
}
