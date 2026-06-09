import { ref, reactive, computed } from "vue";
import * as api from "../api/chat";

// Single shared store so the sidebar and chat area stay in sync.
const conversations = ref([]);
const currentId = ref(null);
const messages = ref([]);
const isStreaming = ref(false);
const suggestions = ref([]);
let controller = null;

const currentConversation = computed(() =>
  conversations.value.find((c) => c.id === currentId.value) || null
);

async function loadConversations() {
  conversations.value = await api.listConversations();
}

async function openConversation(id) {
  if (isStreaming.value) stop();
  suggestions.value = [];
  currentId.value = id;
  const rows = await api.getMessages(id);
  messages.value = rows.map((m) => ({
    role: m.role,
    content: m.content,
    tools: m.extra?.tools || [],
    thinking: m.extra?.thinking || "",
    interrupted: m.extra?.interrupted || false,
    pending: false,
  }));
}

async function newConversation() {
  if (isStreaming.value) stop();
  suggestions.value = [];
  const conv = await api.createConversation();
  conversations.value.unshift(conv);
  currentId.value = conv.id;
  messages.value = [];
}

async function removeConversation(id) {
  await api.deleteConversation(id);
  conversations.value = conversations.value.filter((c) => c.id !== id);
  if (currentId.value === id) {
    currentId.value = null;
    messages.value = [];
  }
}

// Apply a streamed event to the live assistant message.
function applyEvent(ev, assistant) {
  switch (ev.type) {
    case "token":
      assistant.content += ev.content;
      break;
    case "tool_call":
      assistant.tools.push({ id: ev.id, name: ev.name, args: ev.args, result: null });
      break;
    case "tool_result": {
      const step = assistant.tools.find((t) => t.id === ev.id);
      if (step) step.result = ev.content;
      break;
    }
    case "thinking_token":
      assistant.thinking += ev.content;
      break;
    case "title": {
      const conv = conversations.value.find((c) => c.id === currentId.value);
      if (conv) conv.title = ev.title;
      break;
    }
    case "clear_content":
      assistant.content = "";
      break;
    case "interrupted":
      assistant.interrupted = true;
      break;
  }
}

async function runStream(streamFactory, assistant) {
  isStreaming.value = true;
  controller = new AbortController();
  try {
    for await (const ev of streamFactory(controller.signal)) {
      applyEvent(ev, assistant);
    }
  } catch (e) {
    if (e.name === "AbortError") assistant.interrupted = true;
    else {
      assistant.content += `\n\n[error: ${e.message}]`;
      throw e;
    }
  } finally {
    assistant.pending = false;
    isStreaming.value = false;
    controller = null;
    loadConversations(); // refresh order + auto-generated titles
  }
}

async function send(text) {
  const content = text.trim();
  if (!content || isStreaming.value) return;
  if (!currentId.value) await newConversation();

  suggestions.value = [];
  messages.value.push({ role: "user", content, tools: [], pending: false });
  const assistant = reactive({ role: "assistant", content: "", tools: [], thinking: "", interrupted: false, pending: true });
  messages.value.push(assistant);

  const id = currentId.value;
  await runStream((signal) => api.streamMessage(id, content, { signal }), assistant);
  if (!assistant.interrupted && currentId.value === id) {
    suggestions.value = await api.getSuggestions(id).then((r) => r.suggestions).catch(() => []);
  }
}

async function regenerate() {
  if (isStreaming.value || !currentId.value) return;
  suggestions.value = [];
  while (messages.value.length && messages.value.at(-1).role === "assistant") {
    messages.value.pop();
  }
  if (!messages.value.length) return;

  const assistant = reactive({ role: "assistant", content: "", tools: [], thinking: "", interrupted: false, pending: true });
  messages.value.push(assistant);

  const id = currentId.value;
  await runStream((signal) => api.streamRegenerate(id, { signal }), assistant);
  if (!assistant.interrupted && currentId.value === id) {
    suggestions.value = await api.getSuggestions(id).then((r) => r.suggestions).catch(() => []);
  }
}

function stop() {
  if (currentId.value) api.cancelGeneration(currentId.value); // server-side
  if (controller) controller.abort(); // client-side
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
