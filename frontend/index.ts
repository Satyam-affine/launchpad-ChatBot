/**
 * Builder Chat — public frontend API.
 *
 * Prefer importing via the LaunchPad host bridge `@/builder-chat`
 * (see `frontend/src/builder-chat.ts`) so Vite resolves the module reliably.
 * Direct imports from this package remain valid for in-module use.
 */

export {
  BuilderChatError,
  builderChatErrorLabel,
  normalizeBuilderChatMessages,
  sendBuilderChatMessage,
  type BuilderChatErrorCode,
  type BuilderChatMessage,
  type BuilderChatResponse,
} from "./api";

export {
  BuilderChatLauncher,
  BuilderChatPanel,
} from "./BuilderChatWidget";
