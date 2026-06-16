<template>
  <div class="flex h-screen overflow-hidden">
    <Sidebar />
    <main class="flex flex-col flex-1 min-w-0 bg-base-100">
      <header class="navbar min-h-12 px-5 border-b border-base-300 bg-base-100">
        <span class="text-sm font-semibold">{{ currentConversation?.title || "New chat" }}</span>
      </header>
      <MessageList :messages="messages" :can-regenerate="canRegenerate" @regenerate="regenerate" />

      <div v-if="suggestions.length && !isStreaming" class="px-5 pb-2">
        <div class="max-w-3xl mx-auto flex flex-wrap gap-2">
          <button
            v-for="s in suggestions"
            :key="s"
            class="btn btn-ghost btn-sm border border-base-300 text-left h-auto py-2 whitespace-normal font-normal"
            @click="send(s)"
          >{{ s }}</button>
        </div>
      </div>

      <MessageInput
        :is-streaming="isStreaming"
        @send="send"
        @stop="stop"
      />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useChat } from "@/composables/useChat";
import Sidebar from "@/components/Sidebar.vue";
import MessageList from "@/components/MessageList.vue";
import MessageInput from "@/components/MessageInput.vue";

const {
  messages,
  isStreaming,
  suggestions,
  currentConversation,
  loadConversations,
  send,
  regenerate,
  stop,
} = useChat();

const canRegenerate = computed(
  () => messages.value.some((m) => m.role === "assistant") && !isStreaming.value
);

onMounted(loadConversations);
</script>
