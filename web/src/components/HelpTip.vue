<script setup lang="ts">
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

// One line of help for a control: a tooltip on hover and focus, and the same line as the
// control's accessible description (it names `id` in its `aria-describedby`).
const { id, text } = defineProps<{ id: string; text: string }>()
defineSlots<{ default(): unknown }>()
</script>

<template>
  <TooltipProvider>
    <Tooltip v-slot="{ open }">
      <TooltipTrigger as-child><slot /></TooltipTrigger>
      <TooltipContent v-if="open">{{ text }}</TooltipContent>
    </Tooltip>
  </TooltipProvider>
  <span :id="id" class="sr-only">{{ text }}</span>
</template>
