<script setup lang="ts">
import { explained, type Asked } from '../lib/questions'
import { Badge } from '@/components/ui/badge'

// What a choice card holds, the same for one pick and several: the label with Recommended, what
// picking it means, and its preview when it has one. A hidden space stands between the parts, so a
// screen reader reads them apart, as the gaps show them apart.
const { choice } = defineProps<{ choice: Asked['choices'][number] }>()
</script>

<template>
  <span class="flex min-w-0 flex-col gap-1">
    <span class="flex flex-wrap items-center gap-2 font-medium wrap-anywhere">
      <span>{{ choice.text }}</span>
      <span class="sr-only">&nbsp;</span>
      <Badge v-if="choice.recommended" variant="default">Recommended</Badge>
    </span>
    <span class="sr-only">&nbsp;</span>
    <span v-if="explained(choice)" class="text-muted-foreground text-sm wrap-anywhere">{{
      explained(choice)
    }}</span>
    <pre
      v-if="choice.preview"
      class="bg-muted text-foreground mt-1 max-h-48 overflow-auto rounded-md p-2 font-mono text-xs whitespace-pre"
      >{{ choice.preview }}</pre>
  </span>
</template>
