import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowLeft, MessageCircle } from "lucide-react";
import {
  BuilderChatError,
  builderChatErrorLabel,
  normalizeBuilderChatMessages,
  sendBuilderChatMessage,
  type BuilderChatMessage,
  type BuilderChatErrorCode,
} from "./api";
import { ChatInput } from "@/features/launchpad/ChatInput";
import {
  ChatMessage,
  TypingIndicator,
} from "@/features/launchpad/ChatMessage";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const STARTER_PROMPTS = [
  "Explain this project.",
  "How do I run it?",
  "Where is authentication implemented?",
  "Which files implement PDF parsing?",
];

interface BuilderChatSharedProps {
  sessionId: string;
  initialMessages?: BuilderChatMessage[];
  onMessagesChange?: (messages: BuilderChatMessage[]) => void;
}

export interface BuilderChatPanelProps extends BuilderChatSharedProps {
  onClose: () => void;
}

export interface BuilderChatLauncherProps {
  open: boolean;
  onOpen: () => void;
  hidden?: boolean;
}

function useBuilderChatState({
  sessionId,
  initialMessages = [],
  onMessagesChange,
}: BuilderChatSharedProps) {
  const [messages, setMessages] = useState<BuilderChatMessage[]>(
    initialMessages,
  );
  const [draft, setDraft] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<BuilderChatErrorCode | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages(initialMessages);
  }, [sessionId, initialMessages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isTyping) return;
      setError(null);
      setErrorCode(null);
      setDraft("");
      setIsTyping(true);
      try {
        const result = await sendBuilderChatMessage(
          sessionId,
          trimmed,
          messages,
        );
        setMessages(result.messages);
        onMessagesChange?.(result.messages);
      } catch (err) {
        if (err instanceof BuilderChatError) {
          setError(err.message);
          setErrorCode(err.code);
        } else {
          setError(
            err instanceof Error ? err.message : "Failed to send message",
          );
          setErrorCode("unknown");
        }
      } finally {
        setIsTyping(false);
      }
    },
    [isTyping, messages, onMessagesChange, sessionId],
  );

  return {
    messages,
    draft,
    setDraft,
    isTyping,
    error,
    errorCode,
    bottomRef,
    send,
  };
}

/** Full-height chat that fills the right Inspector column. */
export function BuilderChatPanel({
  sessionId,
  initialMessages = [],
  onMessagesChange,
  onClose,
}: BuilderChatPanelProps) {
  const {
    messages,
    draft,
    setDraft,
    isTyping,
    error,
    errorCode,
    bottomRef,
    send,
  } = useBuilderChatState({
    sessionId,
    initialMessages,
    onMessagesChange,
  });

  return (
    <div
      className="flex h-full min-h-0 w-full flex-col bg-background"
      role="region"
      aria-label="Workflow codebase assistant"
    >
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-border bg-surface px-3 py-2.5">
        <div className="min-w-0 flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={onClose}
            aria-label="Back to inspector"
          >
            <ArrowLeft size={16} />
          </Button>
          <div className="min-w-0">
            <p className="text-sm font-semibold leading-tight">
              Codebase assistant
            </p>
            <p className="text-[11px] text-muted-foreground truncate">
              Ask about the published GitHub repository
            </p>
          </div>
        </div>
      </header>

      <div
        className="flex-1 min-h-0 overflow-y-auto px-3 py-3 space-y-3 bg-[var(--lp-chat-bg,transparent)]"
        style={{ "--lp-chat-max-width": "100%" } as React.CSSProperties}
      >
        {messages.length === 0 && !isTyping ? (
          <div className="space-y-3 px-1">
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Ask questions about the GitHub repository generated for this
                  session. Publish code first so answers can be grounded in that
                  repo.
                </p>
            <div className="flex flex-wrap gap-2">
              {STARTER_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={isTyping}
                  onClick={() => void send(prompt)}
                  className="rounded-full border border-border/80 bg-card px-2.5 py-1 text-[11px] text-foreground/90 hover:bg-muted/80 transition-colors disabled:opacity-50"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {messages.map((msg) => (
          <ChatMessage
            key={msg.id}
            message={{
              id: msg.id,
              role: msg.role,
              content: msg.content,
              timestamp: msg.timestamp,
            }}
          />
        ))}

        {isTyping ? <TypingIndicator /> : null}
        {error ? (
          <div
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-2.5 py-2 text-xs text-destructive"
            role="alert"
          >
            {errorCode ? (
              <p className="font-semibold mb-0.5">
                {builderChatErrorLabel(errorCode)}
              </p>
            ) : null}
            <p className="leading-relaxed">{error}</p>
          </div>
        ) : null}
        <div ref={bottomRef} aria-hidden />
      </div>

      <div className="shrink-0 [&_.lp-chat-composer]:border-t [&_.lp-chat-composer]:px-2 [&_.lp-chat-composer]:py-2">
        <ChatInput
          value={draft}
          onChange={setDraft}
          onSend={() => void send(draft)}
          disabled={isTyping}
          placeholder="Ask about your workflow or codebase…"
        />
      </div>
    </div>
  );
}

/** Floating launcher — opens chat into the Inspector panel. */
export function BuilderChatLauncher({
  open,
  onOpen,
  hidden = false,
}: BuilderChatLauncherProps) {
  if (hidden || open) return null;
  if (typeof document === "undefined") return null;

  // Portal to body so AppShell `overflow-hidden` cannot clip the fixed FAB.
  return createPortal(
    <div className="fixed bottom-6 right-6 z-[250] pointer-events-none">
      <Button
        type="button"
        size="icon"
        className="pointer-events-auto h-24 w-24 rounded-full shadow-lg [&_svg]:!size-[42px]"
        onClick={onOpen}
        aria-label="Open codebase assistant"
        aria-expanded={open}
      >
        <MessageCircle size={42} />
      </Button>
    </div>,
    document.body,
  );
}

export { normalizeBuilderChatMessages };
