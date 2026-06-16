<script setup lang="ts">
import { ref, watch, nextTick } from "vue";
import ChatMessage from "./ChatMessage.vue";
import type { Message } from "../types";

const props = defineProps<{
  messages: Message[];
  canRegenerate?: boolean;
}>();

defineEmits<{
  regenerate: [];
}>();

const scroller = ref<HTMLElement | null>(null);

const toBottom = async () => {
  await nextTick();
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
};

watch(() => props.messages, toBottom, { deep: true });
</script>

<template>
  <div ref="scroller" class="flex-1 overflow-y-auto bg-base-100">
    <div class="max-w-3xl mx-auto px-5 py-6">
      <p v-if="!messages.length" class="text-center text-base-content/40 mt-10 text-sm">Send a message to start.</p>
      <ChatMessage
        v-for="(m, i) in messages"
        :key="i"
        :message="m"
        :can-regenerate="canRegenerate && i === messages.length - 1 && m.role === 'assistant'"
        @regenerate="$emit('regenerate')"
      />
    </div>
  </div>
</template>
