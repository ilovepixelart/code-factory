<script setup lang="ts">
import StatusBadge from './StatusBadge.vue'
import { contextText, underFloor, type Model } from '../lib/connections'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

// A server's models as a count that opens to the list, each with its context and, under the
// floor a coding agent needs, the mark; nothing for a server with none.
defineProps<{ models: Model[] }>()
</script>

<template>
  <Collapsible v-if="models.length" :unmount-on-hide="false" class="text-sm text-muted-foreground">
    <CollapsibleTrigger as-child
      ><Button type="button" variant="ghost" size="xs"
        >{{ models.length }} {{ models.length === 1 ? 'model' : 'models' }}</Button
      ></CollapsibleTrigger
    >
    <CollapsibleContent class="mt-1 flex flex-wrap gap-x-3 gap-y-1">
      <span
        v-for="model in models"
        :key="model.id"
        class="inline-flex flex-wrap items-center gap-x-1"
        data-model
        ><code>{{ model.id }}</code
        ><span v-if="contextText(model)">{{ contextText(model) }}</span
        ><StatusBadge v-if="underFloor(model)" tone="warning">Under 64,000</StatusBadge></span
      >
    </CollapsibleContent>
  </Collapsible>
</template>
