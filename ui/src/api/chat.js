// Thin API client. Streaming endpoints are exposed as async generators that
// yield parsed SSE events.

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8080/api";

async function json(res) {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const listConversations = () =>
  fetch(`${BASE}/conversations`).then(json);

export const createConversation = (title) =>
  fetch(`${BASE}/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title ?? null }),
  }).then(json);

export const getMessages = (id) =>
  fetch(`${BASE}/conversations/${id}/messages`).then(json);

export const deleteConversation = (id) =>
  fetch(`${BASE}/conversations/${id}`, { method: "DELETE" }).then(json);

export const renameConversation = (id, title) =>
  fetch(`${BASE}/conversations/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  }).then(json);

// Server-side interrupt (in addition to aborting the fetch client-side).
export const cancelGeneration = (id) =>
  fetch(`${BASE}/conversations/${id}/cancel`, { method: "POST" }).catch(() => {});

export const getSuggestions = (id) =>
  fetch(`${BASE}/conversations/${id}/suggestions`, { method: "POST" }).then(json);

// Parse an SSE byte stream into events. Shared by send + regenerate.
async function* readSSE(res, signal) {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop(); // keep incomplete trailing frame
      for (const frame of frames) {
        const line = frame.trim();
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (payload) yield JSON.parse(payload);
      }
    }
  } finally {
    // ensure the underlying connection is torn down on abort
    if (signal?.aborted) reader.cancel().catch(() => {});
  }
}

export async function* streamMessage(conversationId, content, { signal } = {}) {
  const res = await fetch(`${BASE}/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
    signal,
  });
  yield* readSSE(res, signal);
}

export async function* streamRegenerate(conversationId, { signal } = {}) {
  const res = await fetch(`${BASE}/conversations/${conversationId}/regenerate`, {
    method: "POST",
    signal,
  });
  yield* readSSE(res, signal);
}
