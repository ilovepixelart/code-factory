<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ToolCall } from '../generated/ToolCall'
import { ask } from '../lib/actions'
import { refusalText } from '../lib/notice'
import Tool from './ai/Tool/Tool.vue'

// One tool call's full input and output, fetched only when the person asks for them.
const props = defineProps<{ sessionId: string; seq: number }>()

const name = computed(() => `Input and output of call ${String(props.seq)}`)
const open = ref(false)
const call = ref<ToolCall | null>(null)
const error = ref('')

async function toggle(opened: boolean): Promise<void> {
  open.value = opened
  if (!opened) return
  call.value = null
  error.value = ''
  try {
    call.value = await ask<ToolCall>(
      `/api/sessions/${encodeURIComponent(props.sessionId)}/calls/${String(props.seq)}`,
    )
  } catch (error_) {
    error.value = refusalText(error_)
  }
}
</script>

<template>
  <Tool :open="open" :name="name" :call="call" :error="error" @update:open="toggle($event)" />
</template>
