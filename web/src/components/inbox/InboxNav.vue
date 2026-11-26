<script setup lang="ts">
import type { InboxItem, Section } from '../../lib/metrics'
import type { Paged } from '../../lib/paging'
import PageNav from '../PageNav.vue'
import { pagePrefix } from './inbox'

// The page control under a section's list: the section's own page in the address (CF-1196).
const { section, label, paged } = defineProps<{
  section: Section
  label: string
  paged: Paged<InboxItem>
}>()
</script>

<template>
  <PageNav
    :label="label"
    :prefix="pagePrefix(section)"
    :total="paged.total.value"
    :page="paged.page.value"
    :size="paged.size.value"
  />
</template>
