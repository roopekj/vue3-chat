import { ref, computed } from "vue";
import * as api from "@/api/chat";
import type { Conversation, Message, WsEvent } from "@/types";

interface ConvState {
  messages: Message[];
  isStreaming: boolean;
  loaded: boolean;
  liveAssistant: Message | null;
}

const conversations = ref<Conversation[]>([]);
const currentId = ref<string | null>(null);
const suggestions = ref<string[]>([]);
const convState = ref<Record<string, ConvState>>({});

const ensureState = (id: string): ConvState => {
  if (!convState.value[id]) {
    convState.value[id] = { messages: [], isStreaming: false, loaded: false, liveAssistant: null };
  }
  return convState.value[id];
};

export const currentConversation = computed(() =>
  conversations.value.find((c) => c.id === currentId.value) ?? null
);

export const messages = computed<Message[]>(() =>
  currentId.value ? (convState.value[currentId.value]?.messages ?? []) : []
);

export const isStreaming = computed(() =>
  currentId.value ? (convState.value[currentId.value]?.isStreaming ?? false) : false
);

// ---- WebSocket ----

let ws: WebSocket | null = null;

const handleWsEvent = (event: WsEvent) => {
  const state = ensureState(event.conv_id);
  const assistant = state.liveAssistant;

  switch (event.type) {
    case "token":
      if (assistant) assistant.content += event.content;
      break;
    case "thinking_token":
      if (assistant) assistant.thinking += event.content;
      break;
    case "tool_call":
      if (assistant) assistant.tools.push({ id: event.id, name: event.name, args: event.args, result: null });
      break;
    case "tool_result": {
      if (assistant) {
        const step = assistant.tools.find((t) => t.id === event.id);
        if (step) step.result = event.content;
      }
      break;
    }
    case "title": {
      const conv = conversations.value.find((c) => c.id === event.conv_id);
      if (conv) conv.title = event.title;
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
      if (!assistant?.interrupted && event.conv_id === currentId.value) {
        api.getSuggestions(event.conv_id)
          .then((r: { suggestions: string[] }) => { suggestions.value = r.suggestions; })
          .catch(() => {});
      }
      break;
  }
};

const connectWebSocket = () => {
  if (ws && ws.readyState < WebSocket.CLOSING) return;
  ws = new WebSocket(api.WS_URL);
  ws.onmessage = (e) => {
    try { handleWsEvent(JSON.parse(e.data) as WsEvent); } catch {}
  };
  ws.onclose = () => setTimeout(connectWebSocket, 2000);
  ws.onerror = () => ws?.close();
};

connectWebSocket();

// ---- conversations ----

export const loadConversations = async () => {
  conversations.value = await api.listConversations();
};

export const openConversation = async (id: string) => {
  suggestions.value = [];
  currentId.value = id;
  const state = ensureState(id);
  if (!state.loaded && !state.isStreaming) {
    const rows = await api.getMessages(id);
    state.messages = rows.map((m: { role: string; content: string; extra?: { tools?: unknown[]; thinking?: string; interrupted?: boolean } }) => ({
      role: m.role as Message["role"],
      content: m.content,
      tools: m.extra?.tools ?? [],
      thinking: m.extra?.thinking ?? "",
      interrupted: m.extra?.interrupted ?? false,
      pending: false,
    }));
    state.loaded = true;
  }
};

export const newConversation = async () => {
  suggestions.value = [];
  const conv: Conversation = await api.createConversation();
  conversations.value.unshift(conv);
  currentId.value = conv.id;
  ensureState(conv.id);
};

export const removeConversation = async (id: string) => {
  if (convState.value[id]?.isStreaming) {
    ws?.send(JSON.stringify({ type: "cancel", conv_id: id }));
  }
  await api.deleteConversation(id);
  conversations.value = conversations.value.filter((c) => c.id !== id);
  delete convState.value[id];
  if (currentId.value === id) currentId.value = null;
};

const newAssistantMessage = (): Message => ({
  role: "assistant", content: "", tools: [], thinking: "", interrupted: false, pending: true,
});

export const send = async (text: string) => {
  const content = text.trim();
  if (!content) return;
  if (!currentId.value) await newConversation();

  const id = currentId.value!;
  const state = ensureState(id);
  if (state.isStreaming) return;

  suggestions.value = [];
  state.messages.push({ role: "user", content, tools: [], thinking: "", interrupted: false, pending: false });
  state.messages.push(newAssistantMessage());
  state.liveAssistant = state.messages.at(-1)!;
  state.isStreaming = true;
  state.loaded = true;

  await api.sendMessage(id, content);
};

export const regenerate = async () => {
  if (!currentId.value) return;
  const id = currentId.value;
  const state = ensureState(id);
  if (state.isStreaming) return;

  suggestions.value = [];
  while (state.messages.at(-1)?.role === "assistant") state.messages.pop();
  if (!state.messages.length) return;

  state.messages.push(newAssistantMessage());
  state.liveAssistant = state.messages.at(-1)!;
  state.isStreaming = true;

  await api.regenerateMessage(id);
};

export const stop = () => {
  const id = currentId.value;
  if (!id) return;
  ws?.send(JSON.stringify({ type: "cancel", conv_id: id }));
  api.cancelGeneration(id);
};

export const useChat = () => ({
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
});
