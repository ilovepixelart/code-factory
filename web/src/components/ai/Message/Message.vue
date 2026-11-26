<script setup lang="ts">
import { Bubble, BubbleContent } from '@/components/ui/bubble'
import { Message as MessageRoot, MessageContent } from '@/components/ui/message'

// AI Elements' Message over the words of a ticket's activity entry: the person's turn sits at the
// end in a muted bubble, anyone else's at the start. Line breaks are the writer's, so they stay.
const { text, mine } = defineProps<{ text: string; mine: boolean }>()
</script>

<template>
  <MessageRoot :align="mine ? 'end' : 'start'">
    <MessageContent>
      <Bubble :align="mine ? 'end' : 'start'" variant="muted">
        <BubbleContent class="whitespace-pre-line">{{ text }}</BubbleContent>
      </Bubble>
    </MessageContent>
  </MessageRoot>
</template>
