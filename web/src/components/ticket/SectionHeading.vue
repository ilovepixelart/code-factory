<script setup lang="ts">
import { computed } from 'vue'
import { useSectionLevel } from './context'

// The title of one section of the ticket form; every section takes this one, at the form's
// section level.
const { id } = defineProps<{ id: string }>()
defineSlots<{ default(): unknown }>()
const level = useSectionLevel()
const tag = computed(() => `h${String(level.value)}`)
</script>

<template>
  <component
    :is="tag"
    :id="id"
    data-slot="section-heading"
    class="flex items-center gap-2 text-sm font-semibold"
  >
    <slot />
  </component>
</template>
