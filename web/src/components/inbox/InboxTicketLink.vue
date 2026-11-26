<script setup lang="ts">
import type { InboxItem } from '../../lib/metrics'
import TicketHoverCard from '../TicketHoverCard.vue'

const { item } = defineProps<{ item: InboxItem }>()
</script>

<template>
  <TicketHoverCard
    :repository="item.ticket?.repository ?? ''"
    :ticket="item.ticket?.id ?? ''"
    class="text-muted-foreground min-w-0 truncate hover:underline"
    ><span class="font-mono">{{ item.ticket?.id }}</span> {{ item.ticket?.title }}</TicketHoverCard
  >
</template>
