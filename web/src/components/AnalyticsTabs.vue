<script setup lang="ts">
import { computed } from 'vue'
import type { LocationQueryRaw } from 'vue-router'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ANALYTICS_TABS } from '../lib/analytics'
// The switch between the Analytics pages, in the header; `query` carries the range to each tab.
// Each tab is a link: the address names the page.
const { page, query = {} } = defineProps<{
  /** The address of the page showing, one of `ANALYTICS_TABS`. */
  page: string
  query?: LocationQueryRaw
}>()
const options = computed(() =>
  ANALYTICS_TABS.map(([path, label]) => ({ path, label, to: { path, query } })),
)
</script>

<template>
  <Teleport to="#header-controls">
    <nav aria-label="Analytics pages">
      <Tabs :model-value="page" activation-mode="manual">
        <TabsList>
          <TabsTrigger v-for="option in options" :key="option.path" :value="option.path" as-child>
            <RouterLink :to="option.to" :aria-current="page === option.path ? 'page' : undefined">{{
              option.label
            }}</RouterLink>
          </TabsTrigger>
        </TabsList>
      </Tabs>
    </nav>
  </Teleport>
</template>
