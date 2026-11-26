<script setup lang="ts">
import SectionCard from '../SectionCard.vue'
import { HugeiconsIcon } from '@hugeicons/vue'
import type { Icon } from '../../lib/icon'
import type { Paged } from '../../lib/paging'
import { GROUP_SIZE, type TeamRow as Row } from '../../lib/teamNow'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import PageNav from '../PageNav.vue'
import TeamTable from './TeamTable.vue'
import { inject } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ATTENTION } from '../../lib/attention'

// One group of the Team page (CF-1162): its header and count, its rows in one surface or its
// empty line, then what it adds under its rows (the idle agents). It draws one page of its rows,
// `paged` under `prefix` in the address (CF-1209).
const { id, title, hint, empty, next, icon, paged, now, selected, prefix, inbox } = defineProps<{
  id: string
  title: string
  hint: string
  empty: string
  next: string
  icon: Icon
  paged: Paged<Row>
  now: number
  selected: string
  prefix: string
  inbox?: boolean
}>()
const emit = defineEmits<{ select: [key: string] }>()
defineSlots<{ default?: () => unknown }>()
// A group answered in the Inbox links there, with the Inbox's own count: the sidebar's number.
const attention = inject(ATTENTION, null)
</script>

<template>
  <SectionCard
    :heading="id"
    :title="title"
    :count="paged.total.value"
    :description="hint"
    :empty="!paged.total.value"
  >
    <template v-if="inbox" #action>
      <Button as-child variant="ghost"
        ><RouterLink to="/inbox"
          >Open the Inbox
          <Badge v-if="attention" variant="secondary">{{
            attention.count.value
          }}</Badge></RouterLink
        ></Button
      >
    </template>
    <template #empty>
      <Empty
        ><EmptyHeader
          ><EmptyMedia variant="icon"><HugeiconsIcon :icon="icon" aria-hidden="true" /></EmptyMedia
          ><EmptyTitle>{{ empty }}</EmptyTitle
          ><EmptyDescription>{{ next }}</EmptyDescription></EmptyHeader
        ></Empty
      >
    </template>
    <div v-if="paged.total.value">
      <TeamTable
        :rows="paged.rows.value"
        :caption="title"
        :now="now"
        :selected="selected"
        @select="emit('select', $event)"
      />
      <slot />
    </div>
    <slot v-else />
    <PageNav
      :label="title.toLowerCase()"
      :prefix="prefix"
      :fallback="GROUP_SIZE"
      :total="paged.total.value"
      :page="paged.page.value"
      :size="paged.size.value"
    />
  </SectionCard>
</template>
