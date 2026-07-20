const API_BASE = import.meta.env.VITE_AFFINE_API_BASE ?? "";
const CHAT_TIMEOUT_MS = 90_000;

export type BuilderChatErrorCode =
  | "session_not_found"
  | "workflow_empty"
  | "llm_not_configured"
  | "llm_failed"
  | "invalid_session_id"
  | "invalid_message"
  | "repo_not_published"
  | "github_not_connected"
  | "repo_fetch_failed"
  | "builder_chat_error"
  | "unknown";

export interface BuilderChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}

export interface BuilderChatResponse {
  reply: string;
  messages: BuilderChatMessage[];
  context_sources: string[];
}

export class BuilderChatError extends Error {
  status: number;
  code: BuilderChatErrorCode;

  constructor(
    message: string,
    status: number,
    code: BuilderChatErrorCode = "unknown",
  ) {
    super(message);
    this.name = "BuilderChatError";
    this.status = status;
    this.code = code;
  }
}

function chatUrl(sessionId: string): string {
  const base = API_BASE.replace(/\/$/, "");
  return `${base}/api/sessions/${encodeURIComponent(sessionId)}/builder/chat`;
}

function parseErrorDetail(raw: unknown): {
  message: string;
  code: BuilderChatErrorCode;
} {
  if (typeof raw === "string" && raw.trim()) {
    const lower = raw.toLowerCase();
    if (lower.includes("session not found")) {
      return { message: raw, code: "session_not_found" };
    }
    if (lower.includes("internal server error")) {
      return {
        message:
          "The server encountered an unexpected error. Check backend logs and try again.",
        code: "unknown",
      };
    }
    return { message: raw, code: "unknown" };
  }
  if (raw && typeof raw === "object") {
    const obj = raw as { message?: string; code?: string };
    const message =
      typeof obj.message === "string" && obj.message.trim()
        ? obj.message
        : "Builder chat failed";
    const code = (obj.code as BuilderChatErrorCode | undefined) ?? "unknown";
    return { message, code };
  }
  return { message: "Builder chat failed", code: "unknown" };
}

function inferErrorCode(status: number, message: string): BuilderChatErrorCode {
  const lower = message.toLowerCase();
  if (status === 503 && lower.includes("not configured")) {
    return "llm_not_configured";
  }
  if (status === 404 && lower.includes("not found")) {
    return "session_not_found";
  }
  if (status === 422 && lower.includes("no workflow")) {
    return "workflow_empty";
  }
  if (status === 422 && lower.includes("published")) {
    return "repo_not_published";
  }
  if (status === 401 && lower.includes("github")) {
    return "github_not_connected";
  }
  if (status === 502 || status === 408) {
    return "llm_failed";
  }
  return "unknown";
}

async function parseErrorResponse(
  res: Response,
): Promise<{ message: string; code: BuilderChatErrorCode }> {
  const raw = await res.text();
  const trimmed = raw.trim();

  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed) as { detail?: unknown };
      if (parsed.detail !== undefined) {
        return parseErrorDetail(parsed.detail);
      }
    } catch {
      /* fall through to plain-text handling */
    }
  }

  if (trimmed) {
    const fromDetail = parseErrorDetail(trimmed);
    if (fromDetail.code !== "unknown") {
      return fromDetail;
    }
    return {
      message: trimmed,
      code: inferErrorCode(res.status, trimmed),
    };
  }

  return {
    message: `Request failed (${res.status} ${res.statusText || "error"})`,
    code: inferErrorCode(res.status, res.statusText || ""),
  };
}

export function builderChatErrorLabel(code: BuilderChatErrorCode): string {
  switch (code) {
    case "session_not_found":
      return "Session not found";
    case "workflow_empty":
      return "No workflow steps";
    case "llm_not_configured":
      return "AI not configured";
    case "llm_failed":
      return "AI request failed";
    case "invalid_session_id":
      return "Invalid session";
    case "repo_not_published":
      return "Repository not published";
    case "github_not_connected":
      return "GitHub not connected";
    case "repo_fetch_failed":
      return "Could not read repository";
    default:
      return "Chat error";
  }
}

export async function sendBuilderChatMessage(
  sessionId: string,
  message: string,
  history: BuilderChatMessage[],
): Promise<BuilderChatResponse> {
  const trimmedSessionId = sessionId.trim();
  if (!trimmedSessionId) {
    throw new BuilderChatError(
      "No session id is available for builder chat.",
      400,
      "invalid_session_id",
    );
  }

  const url = chatUrl(trimmedSessionId);
  if (import.meta.env.DEV) {
    console.debug("[BuilderChat] POST", {
      sessionId: trimmedSessionId,
      url,
      historyTurns: history.length,
      messagePreview: message.slice(0, 120),
    });
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history: history.map(({ role, content }) => ({ role, content })),
      }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const parsed = await parseErrorResponse(res);
      throw new BuilderChatError(parsed.message, res.status, parsed.code);
    }
    return (await res.json()) as BuilderChatResponse;
  } catch (error) {
    if (error instanceof BuilderChatError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new BuilderChatError("Request timed out", 408, "llm_failed");
    }
    if (error instanceof TypeError) {
      throw new BuilderChatError(
        "Could not reach the backend. Check that the API server is running.",
        0,
        "unknown",
      );
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export function normalizeBuilderChatMessages(
  raw: unknown,
): BuilderChatMessage[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(
      (item): item is BuilderChatMessage =>
        Boolean(item) &&
        typeof item === "object" &&
        (item as BuilderChatMessage).role !== undefined &&
        typeof (item as BuilderChatMessage).content === "string",
    )
    .map((item) => ({
      id: item.id || `bcm_${crypto.randomUUID().slice(0, 8)}`,
      role: item.role,
      content: item.content,
      timestamp: item.timestamp,
    }));
}
