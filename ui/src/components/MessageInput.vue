<script setup lang="ts">
import { ref } from "vue";

const props = defineProps<{
  isStreaming?: boolean;
}>();

const emit = defineEmits<{
  send: [text: string];
  stop: [];
}>();

const text = ref("");

const submit = () => {
  if (props.isStreaming) return;
  const v = text.value.trim();
  if (!v) return;
  emit("send", v);
  text.value = "";
};

const onKeydown = (e: KeyboardEvent) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submit();
  }
};
</script>

<template>
  <div class="border-t border-base-300 bg-base-100 px-5 pb-5 pt-3">
    <div class="max-w-3xl mx-auto flex flex-col gap-2">
      <div class="flex items-end gap-2 border border-base-300 rounded-2xl px-4 py-2 bg-base-200 focus-within:border-primary transition-colors">
        <textarea
          v-model="text"
          class="flex-1 bg-transparent border-none outline-none resize-none text-sm leading-relaxed max-h-44 font-[inherit] text-base-content placeholder:text-base-content/30"
          rows="1"
          placeholder="Message…  (Enter to send, Shift+Enter for newline)"
          @keydown="onKeydown"
        ></textarea>

        <button
          v-if="isStreaming"
          class="btn btn-sm btn-circle btn-neutral shrink-0"
          title="Stop"
          @click="emit('stop')"
        >■</button>
        <button
          v-else
          class="btn btn-sm btn-circle btn-primary shrink-0"
          :disabled="!text.trim()"
          title="Send"
          @click="submit"
        >↑</button>
      </div>
    </div>
  </div>
</template>
