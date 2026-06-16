<script setup lang="ts">
import { computed, ref } from "vue";
import { renderMarkdown } from "../utils/markdown";
import type { Message } from "../types";

const props = defineProps<{
  message: Message;
  canRegenerate?: boolean;
}>();

const emit = defineEmits<{
  regenerate: [];
}>();

const renderedContent = computed(() => renderMarkdown(props.message.content));

const copied = ref(false);

const copyContent = async () => {
  await navigator.clipboard.writeText(props.message.content);
  copied.value = true;
  setTimeout(() => (copied.value = false), 1500);
};
</script>

<template>
  <div
    class="chat"
    :class="message.role === 'user' ? 'chat-end' : 'chat-start'"
  >
    <div
      class="chat-bubble text-sm leading-relaxed break-words"
      :class="
        message.role === 'user' ? 'chat-bubble-primary' : 'chat-bubble-neutral'
      "
    >
      <!-- thinking -->
      <details
        v-if="message.thinking"
        class="bg-base-300/40 border border-base-content/10 rounded-lg px-3 py-2 mb-2 text-xs"
        open
      >
        <summary class="font-semibold text-base-content/70 cursor-pointer select-none">💭 Thinking</summary>
        <div class="mt-1 whitespace-pre-wrap font-mono text-base-content/60">{{ message.thinking }}</div>
      </details>

      <!-- tool steps -->
      <div
        v-for="t in message.tools"
        :key="t.id"
        class="bg-base-300/40 border border-base-content/10 rounded-lg px-3 py-2 mb-2 font-mono text-xs"
      >
        <div class="font-semibold text-base-content/70">
          🔧 {{ t.name }}({{ JSON.stringify(t.args) }})
        </div>
        <div v-if="t.result" class="mt-1 whitespace-pre-wrap">
          {{ t.result }}
        </div>
        <div v-else class="mt-1 text-base-content/50 italic">running…</div>
      </div>

      <!-- eslint-disable-next-line vue/no-v-html -->
      <div v-if="message.content" class="md-body text-sm" v-html="renderedContent" />

      <span
        v-if="message.pending && !message.content && !message.tools.length"
        class="animate-pulse"
        >▋</span
      >

      <div v-if="message.interrupted" class="mt-2 text-xs opacity-60">
        ⏹ stopped
      </div>

      <div v-if="message.content && !message.pending" class="mt-2 flex justify-end gap-1">
        <button class="btn btn-ghost btn-xs opacity-60 hover:opacity-100" @click="copyContent">
          {{ copied ? "✓ Copied" : "⎘ Copy" }}
        </button>
        <button v-if="canRegenerate" class="btn btn-ghost btn-xs opacity-60 hover:opacity-100" @click="emit('regenerate')">
          ↻ Regenerate
        </button>
      </div>
    </div>
  </div>
</template>
