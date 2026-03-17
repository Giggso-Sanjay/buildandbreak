/**
 * Chat API client - calls /chat endpoint using env-configured base URL.
 * Uses hardcoded JWT Bearer token for auth (testing; no expiration).
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const AUTH_TOKEN =
  import.meta.env.VITE_API_AUTH_TOKEN ??
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJpYXQiOjE3MzU2ODk2MDAsImV4cCI6NDA3MDkwODgwMH0.49JDWZ45SFFkBSQUV9aiy682SvKMcOpfhTRF1rhMNy4";

export interface DatasourceFile {
  name: string;
  content: string;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  datasources?: DatasourceFile[];
}

export interface ChatResponse {
  reply: string;
  provider: string;
  model: string;
  raw: Record<string, unknown>;
}

/**
 * Sends a message to the /chat endpoint.
 * Pass datasources to create ml_knowledge_base.json before each query.
 */
export async function sendChatMessage(
  message: string,
  sessionId?: string,
  datasources?: DatasourceFile[]
): Promise<ChatResponse> {
  const url = `${API_BASE.replace(/\/$/, "")}/chat`;
  const body: ChatRequest = {
    message,
    session_id: sessionId ?? undefined,
    datasources: datasources?.length ? datasources : undefined,
  };
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${AUTH_TOKEN}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Chat API error: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<ChatResponse>;
}

/**
 * Clears session: deletes ml_knowledge_base.json on backend.
 */
export async function clearSession(): Promise<void> {
  const url = `${API_BASE.replace(/\/$/, "")}/clear-session`;
  const res = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${AUTH_TOKEN}` },
  });
  if (!res.ok) {
    throw new Error(`Clear session failed: ${res.status}`);
  }
}
