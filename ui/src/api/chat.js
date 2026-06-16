// Thin API client.

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8080/api";

// Derive WS URL from the HTTP base (http -> ws, https -> wss).
export const WS_URL = BASE.replace(/^http/, "ws") + "/ws";

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

export const cancelGeneration = (id) =>
  fetch(`${BASE}/conversations/${id}/cancel`, { method: "POST" }).catch(() => {});

export const getSuggestions = (id) =>
  fetch(`${BASE}/conversations/${id}/suggestions`, { method: "POST" }).then(json);

// Send a message — generation events arrive over the WebSocket, not in the response.
export const sendMessage = (id, content) =>
  fetch(`${BASE}/conversations/${id}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  }).then(json);

// Regenerate — same pattern.
export const regenerateMessage = (id) =>
  fetch(`${BASE}/conversations/${id}/regenerate`, { method: "POST" }).then(json);
