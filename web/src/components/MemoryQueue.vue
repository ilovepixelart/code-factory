<script setup lang="ts" generic="T">
import SectionCard from './SectionCard.vue'
import ContentCard from './ContentCard.vue'
import { computed, nextTick, ref, useTemplateRef } from 'vue'
import { Button } from '@/components/ui/button'

// One queue of the Memory page: its first rows, and the rest behind one button (CF-1171-R1).
const props = defineProps<{
  id: string
  title: string
  hint?: string
  rows: T[]
  keyOf: (row: T) => string
}>()
const SHOWN = 3
const FOCUSABLE = 'a[href], button:not([disabled]), input, select, textarea, summary'
defineSlots<{ row: (scope: { row: T }) => unknown }>()
const all = ref(false)
const shown = computed(() => (all.value ? props.rows : props.rows.slice(0, SHOWN)))
const hidden = computed(() => props.rows.length - shown.value.length)
const list = useTemplateRef<HTMLUListElement>('list')

// The button leaves with the click: focus goes to the first row it revealed.
async function showAll(): Promise<void> {
  all.value = true
  await nextTick()
  const row = list.value?.children[SHOWN]
  const control = row?.querySelector<HTMLElement>(FOCUSABLE)
  if (control) control.focus()
  else if (row instanceof HTMLElement) {
    row.tabIndex = -1
    row.focus()
  }
}
</script>

<template>
  <SectionCard :heading="id" :title="title" :count="rows.length" :description="hint ?? ''">
    <ul ref="list" class="flex flex-col gap-3">
      <li v-for="row in shown" :key="keyOf(row)">
        <ContentCard><slot name="row" :row="row" /></ContentCard>
      </li>
      <li v-if="hidden > 0">
        <Button type="button" variant="ghost" @click="showAll()"> Show {{ hidden }} more </Button>
      </li>
    </ul>
  </SectionCard>
</template>
