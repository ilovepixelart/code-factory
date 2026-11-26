<script setup lang="ts">
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

// A single line value, cut with an ellipsis where its box ends, its whole text in a tooltip
// (CF-1292): a branch, a label, an assignee, a tool name. The cut box is bounded, so a table cell
// holding one stays inside its table.
// The content mounts only while open: a closed one still holds a teleport and its anchors in
// <body>, one pair per value on a page of many.
defineProps<{ text: string }>()
</script>

<template>
  <span class="inline-flex max-w-[min(32rem,70vw)] min-w-0 align-bottom">
    <TooltipProvider>
      <Tooltip v-slot="{ open }">
        <TooltipTrigger as-child>
          <span class="min-w-0 truncate">{{ text }}</span>
        </TooltipTrigger>
        <TooltipContent v-if="open">{{ text }}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  </span>
</template>
