<template>
  <aside class="flex flex-col w-64 shrink-0 bg-base-200 border-r border-base-300 p-3 gap-3">
    <button class="btn btn-neutral btn-sm w-full" @click="newConversation">+ New chat</button>

    <nav class="flex-1 overflow-y-auto flex flex-col gap-1">
      <button
        v-for="c in conversations"
        :key="c.id"
        class="group flex items-center justify-between w-full px-3 py-2 rounded-lg text-sm text-left transition-colors"
        :class="c.id === currentId ? 'bg-base-300' : 'hover:bg-base-300/60'"
        @click="openConversation(c.id)"
      >
        <span class="truncate">{{ c.title }}</span>
        <span
          class="opacity-0 group-hover:opacity-100 text-base-content/40 hover:text-base-content ml-1 text-lg leading-none transition-opacity"
          @click.stop="onDelete($event, c.id)"
        >×</span>
      </button>
      <p v-if="!conversations.length" class="text-xs text-base-content/40 px-2 py-2">No conversations yet</p>
    </nav>
  </aside>
</template>

<script setup lang="ts">
import { useChat } from "@/composables/useChat";

const { conversations, currentId, newConversation, openConversation, removeConversation } = useChat();

const onDelete = (e: MouseEvent, id: string) => {
  e.stopPropagation();
  if (confirm("Delete this conversation?")) removeConversation(id);
};
</script>
