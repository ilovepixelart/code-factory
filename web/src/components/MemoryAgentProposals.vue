<script setup lang="ts">
import { sentence } from '../lib/format'
import { Badge } from '@/components/ui/badge'
import { entryPath, itemActions } from '../lib/itemActions'
import { usePressed } from '../lib/pressed'
import type { MemoryRecord } from '../lib/memory'
import MemoryQueue from './MemoryQueue.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { FieldError } from '@/components/ui/field'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemFooter,
  ItemTitle,
} from '@/components/ui/item'

// The entries agents proposed (CF-1168): none loads until Approve; Dismiss moves it to the
// history (CF-1171-R1).
const { proposed } = defineProps<{ proposed: MemoryRecord[] }>()
const emit = defineEmits<{ changed: [] }>()
const { busy, errors, run } = itemActions(() => {
  emit('changed')
})
const keyOf = (r: MemoryRecord): string => `${r.repository}/${r.id}`
const { press, spins } = usePressed()
</script>

<template>
  <MemoryQueue
    id="memory-agent-proposals"
    title="Proposed by agents"
    hint="Nothing here loads until you approve it"
    :rows="proposed"
    :key-of="keyOf"
  >
    <template #row="{ row: r }">
      <Item as="article" :aria-label="r.statement" class="items-start py-3">
        <ItemContent class="min-w-0 max-sm:basis-full">
          <ItemTitle class="line-clamp-none wrap-anywhere">{{ r.statement }}</ItemTitle>
          <ItemDescription v-if="r.why" class="line-clamp-none wrap-anywhere"
            >Why: {{ r.why }}</ItemDescription
          >
          <div class="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
            <Badge variant="outline">{{ sentence(r.kind) }}</Badge
            ><span>{{ r.source }}</span
            ><span>would load in {{ r.loads }}</span
            ><span>{{ r.repository }}</span>
          </div>
        </ItemContent>
        <ItemActions>
          <Button
            type="button"
            variant="secondary"
            :disabled="busy.has(keyOf(r))"
            @click="
              press(`approve ${keyOf(r)}`, () =>
                run(keyOf(r), 'POST', `${entryPath(r.repository, r.id)}/approve`),
              )
            "
          >
            <Spinner
              v-if="spins(`approve ${keyOf(r)}`, busy.has(keyOf(r)))"
              data-icon="inline-start"
            />Approve
          </Button>
          <Button
            type="button"
            variant="ghost"
            :disabled="busy.has(keyOf(r))"
            @click="
              press(`dismiss ${keyOf(r)}`, () =>
                run(keyOf(r), 'POST', `${entryPath(r.repository, r.id)}/dismiss`),
              )
            "
          >
            <Spinner
              v-if="spins(`dismiss ${keyOf(r)}`, busy.has(keyOf(r)))"
              data-icon="inline-start"
            />Dismiss
          </Button>
        </ItemActions>
        <ItemFooter v-if="errors[keyOf(r)]"
          ><FieldError>{{ errors[keyOf(r)] }}</FieldError></ItemFooter
        >
      </Item>
    </template>
  </MemoryQueue>
</template>
