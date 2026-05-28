import type { ChatSession, ChatSessionRecord } from "../types";

export function createChatSession(title: string, assistantText?: string): ChatSession {
  const now = new Date().toISOString();
  return {
    id: `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    title,
    pinned: false,
    createdAt: now,
    updatedAt: now,
    messages: [
      {
        role: "assistant",
        text: assistantText ?? "Ready.",
      },
    ],
  };
}

export function mapChatSessionRecord(record: ChatSessionRecord): ChatSession {
  return {
    id: record.id,
    user_id: record.user_id,
    title: record.title,
    pinned: record.pinned,
    createdAt: record.created_at,
    updatedAt: record.updated_at,
    messages: record.messages.map((message) => ({
      role: message.role,
      text: message.text,
      actions: message.actions ?? [],
      citations: message.citations ?? [],
    })),
  };
}

export function loadStoredChatSessions(userId: string, fallbackText?: string) {
  const fallback = createChatSession("Training chat", fallbackText);
  try {
    const raw = localStorage.getItem(`gymflow-chat-sessions-${userId}`);
    if (!raw) {
      return { sessions: [fallback], activeId: fallback.id };
    }
    const parsed = JSON.parse(raw) as { sessions?: ChatSession[]; activeId?: string };
    const sessions = Array.isArray(parsed.sessions) && parsed.sessions.length > 0 ? parsed.sessions : [fallback];
    const activeId = parsed.activeId && sessions.some((session) => session.id === parsed.activeId) ? parsed.activeId : sessions[0].id;
    return { sessions, activeId };
  } catch {
    return { sessions: [fallback], activeId: fallback.id };
  }
}
