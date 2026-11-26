<script setup lang="ts">
import { Skeleton } from '@/components/ui/skeleton'

// The outline of a page's sections while it is read: rows of a table, sections of a list, a grid
// of cards, tiles over a chart, or a document. Skeletons only: a section's Card is drawn once its
// answer is in (docs/design.md, Page anatomy).
export type ReadShape = 'table' | 'list' | 'cards' | 'tiles' | 'document'
const { shape } = defineProps<{ shape: ReadShape }>()
const ROWS = 6
</script>

<template>
  <div v-if="shape === 'table'" class="flex flex-col gap-4" :data-read-shape="shape">
    <Skeleton class="h-6 w-48" />
    <div v-for="row in ROWS" :key="row" class="flex gap-4">
      <Skeleton class="h-4 w-20" />
      <Skeleton class="h-4 flex-1" />
      <Skeleton class="h-4 w-24" />
      <Skeleton class="h-4 w-20" />
    </div>
  </div>
  <div v-else-if="shape === 'list'" class="flex flex-col gap-8" :data-read-shape="shape">
    <div v-for="section in 2" :key="section" class="flex flex-col gap-3">
      <Skeleton class="h-4 w-40" />
      <Skeleton class="h-3 w-64" />
      <Skeleton v-for="row in 3" :key="row" class="h-10 w-full" />
    </div>
  </div>
  <div
    v-else-if="shape === 'cards'"
    class="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3"
    :data-read-shape="shape"
  >
    <Skeleton v-for="card in ROWS" :key="card" class="h-40 w-full rounded-xl" />
  </div>
  <div v-else-if="shape === 'tiles'" class="flex flex-col gap-4" :data-read-shape="shape">
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Skeleton v-for="tile in 4" :key="tile" class="h-24 w-full rounded-xl" />
    </div>
    <Skeleton class="h-80 w-full rounded-xl" />
  </div>
  <div v-else class="flex flex-col gap-6" :data-read-shape="shape">
    <div class="flex flex-col gap-2">
      <Skeleton class="h-3 w-20" />
      <Skeleton class="h-7 w-2/3" />
    </div>
    <div v-for="part in 3" :key="part" class="flex flex-col gap-2">
      <Skeleton class="h-4 w-32" />
      <Skeleton class="h-4 w-full" />
      <Skeleton class="h-4 w-full" />
      <Skeleton class="h-4 w-3/4" />
    </div>
  </div>
</template>
