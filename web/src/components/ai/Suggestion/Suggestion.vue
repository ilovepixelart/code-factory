<script setup lang="ts">
import type { ButtonVariants } from '@/components/ui/button'
import { Button } from '@/components/ui/button'

// AI Elements' Suggestion: a prompt sent in one click, its label the message.
const {
  suggestion,
  variant = 'outline',
  disabled,
} = defineProps<{
  suggestion: string
  variant?: ButtonVariants['variant']
  disabled?: boolean
}>()
const emit = defineEmits<{ click: [suggestion: string] }>()
/** Words after the label inside the button, such as a mark on a recommended choice. */
defineSlots<{ default?: () => unknown }>()
</script>

<template>
  <Button
    type="button"
    :variant="variant"
    size="sm"
    class="shrink-0"
    :disabled="disabled"
    @click="emit('click', suggestion)"
  >
    {{ suggestion }}<slot />
  </Button>
</template>
