import { ref, reactive, computed } from "vue";
import * as api from "../api/chat";

// Module-level singletons so sidebar and chat area share state.
const conversations = ref([]);
const currentId = ref(null);
const suggestions = ref([]);

// Per-conversation live state keyed by conversation ID.
const convState = reactive({});

function ensureState(id) {
  if (!convState[id]) {
    convState[id] = { messages: [], isStreaming: false, loaded: false, liveAssistant: null };
  }
  return convState[id];
}

const currentConversation = computed(() =>
  conversations.value.find((c) => c.id === currentId.value) || null
);

// Computed refs so the UI always reflects the current conversation's live state.
const messages = computed(() =>
  currentId.value ? (convState[currentId.value]?.messages ?? []) : []
);

const isStreaming = computed(() =>
  currentId.value ? (convState[currentId.value]?.isStreaming ?? false) : false
);

// ---- WebSocket ----

let ws = null;

function connectWebSocket() {
  if (ws && ws.readyState < WebSocket.CLOSING) return;
  ws = new WebSocket(api.WS_URL);
  ws.onmessage = (e) => {
    try { handleWsEvent(JSON.parse(e.data)); } catch {}
  };
  ws.onclose = () => setTimeout(connectWebSocket, 2000);
  ws.onerror = () => ws.close();
}

function handleWsEvent(event) {
  const { conv_id, ...ev } = event;
  if (!conv_id) return;
  const state = ensureState(conv_id);
  const assistant = state.liveAssistant;

  switch (ev.type) {
    case "token":
      if (assistant) assistant.content += ev.content;
      break;
    case "tool_call":
      if (assistant) assistant.tools.push({ id: ev.id, name: ev.name, args: ev.args, result: null });
      break;
    case "tool_result": {
      if (assistant) {
        const step = assistant.tools.find((t) => t.id === ev.id);
        if (step) step.result = ev.content;
      }
      break;
    }
    case "thinking_token":
      if (assistant) assistant.thinking += ev.content;
      break;
    case "title": {
      const conv = conversations.value.find((c) => c.id === conv_id);
      if (conv) conv.title = ev.title;
      break;
    }
    case "clear_content":
      if (assistant) assistant.content = "";
      break;
    case "interrupted":
      if (assistant) assistant.interrupted = true;
      break;
    case "end":
      if (assistant) assistant.pending = false;
      state.liveAssistant = null;
      state.isStreaming = false;
      loadConversations();
      if (!assistant?.interrupted && conv_id === currentId.value) {
        api.getSuggestions(conv_id)
          .then((r) => { suggestions.value = r.suggestions ?? []; })
          .catch(() => {});
      }
      break;
  }
}

// Establish connection when the module is first loaded.
connectWebSocket();

// ---- conversations ----

async function loadConversations() {
  conversations.value = await api.listConversations();
}

async function openConversation(id) {
  suggestions.value = [];
  currentId.value = id;
  const state = ensureState(id);
  // Only fetch from the server if the conversation isn't already in memory.
  if (!state.loaded && !state.isStreaming) {
    const rows = await api.getMessages(id);
    state.messages = rows.map((m) => ({
      role: m.role,
      content: m.content,
      tools: m.extra?.tools || [],
      thinking: m.extra?.thinking || "",
      interrupted: m.extra?.interrupted || false,
      pending: false,
    }));
    state.loaded = true;
  }
}

async function newConversation() {
  suggestions.value = [];
  const conv = await api.createConversation();
  conversations.value.unshift(conv);
  currentId.value = conv.id;
  ensureState(conv.id);
}

async function removeConversation(id) {
  const state = convState[id];
  if (state?.isStreaming) {
    ws?.send(JSON.stringify({ type: "cancel", conv_id: id }));
  }
  await api.deleteConversation(id);
  conversations.value = conversations.value.filter((c) => c.id !== id);
  delete convState[id];
  if (currentId.value === id) currentId.value = null;
}

async function send(text) {
  const content = text.trim();
  if (!content) return;
  if (!currentId.value) await newConversation();

  const id = currentId.value;
  const state = ensureState(id);
  if (state.isStreaming) return;

  suggestions.value = [];
  state.messages.push({ role: "user", content, tools: [], pending: false });
  const assistant = reactive({ role: "assistant", content: "", tools: [], thinking: "", interrupted: false, pending: true });
  state.messages.push(assistant);
  state.liveAssistant = assistant;
  state.isStreaming = true;
  state.loaded = true;

  await api.sendMessage(id, content);
}

async function regenerate() {
  if (!currentId.value) return;
  const id = currentId.value;
  const state = ensureState(id);
  if (state.isStreaming) return;

  suggestions.value = [];
  while (state.messages.length && state.messages.at(-1).role === "assistant") {
    state.messages.pop();
  }
  if (!state.messages.length) return;

  const assistant = reactive({ role: "assistant", content: "", tools: [], thinking: "", interrupted: false, pending: true });
  state.messages.push(assistant);
  state.liveAssistant = assistant;
  state.isStreaming = true;

  await api.regenerateMessage(id);
}

function stop() {
  const id = currentId.value;
  if (!id) return;
  ws?.send(JSON.stringify({ type: "cancel", conv_id: id }));
  api.cancelGeneration(id);
}

export function useChat() {
  return {
    conversations,
    currentId,
    currentConversation,
    messages,
    isStreaming,
    suggestions,
    loadConversations,
    openConversation,
    newConversation,
    removeConversation,
    send,
    regenerate,
    stop,
  };
}
