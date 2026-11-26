<script setup lang="ts">
import { ArrowUp02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import { Spinner } from '@/components/ui/spinner'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from '@/components/ui/input-group'

const { label, placeholder, send, busy, sending } = defineProps<{
  label: string
  placeholder: string
  /** The send button's accessible name. */
  send: string
  busy: boolean
  /** Whether this field's words are being sent: its button shows a Spinner. */
  sending?: boolean
}>()
const emit = defineEmits<{ send: [] }>()
// AI Elements' Prompt Input: a field with its send button, which waits for words. It sits inside
// the ticket's own form, so it is no form of its own and sends on its button only: Enter keeps
// adding a line, as in every other field of the ticket. The board takes no attachments here.
const text = defineModel<string>({ required: true })
const canSend = computed(() => !busy && text.value.trim().length > 0)
</script>

<template>
  <InputGroup>
    <InputGroupTextarea
      v-model="text"
      rows="2"
      class="p-3"
      :aria-label="label"
      :placeholder="placeholder"
    />
    <InputGroupAddon align="block-end">
      <InputGroupButton
        size="icon-sm"
        variant="default"
        class="ml-auto rounded-full"
        :aria-label="send"
        :disabled="!canSend"
        @click="emit('send')"
      >
        <Spinner v-if="sending" />
        <HugeiconsIcon v-else :icon="ArrowUp02Icon" aria-hidden="true" />
      </InputGroupButton>
    </InputGroupAddon>
  </InputGroup>
</template>
