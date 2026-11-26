<script setup lang="ts">
import SectionCard from '../SectionCard.vue'
import { ItemGroup } from '@/components/ui/item'
import type { InboxItem } from '../../lib/metrics'
import { itemHref, useInbox, useSectionPage } from './inbox'
import InboxNav from './InboxNav.vue'
import InboxRow from './InboxRow.vue'

// What the coordinator found on a ticket, newest first: it needs no reply, so it is not counted.
const { items } = defineProps<{ items: InboxItem[] }>()
const { now } = useInbox()
const { paged } = useSectionPage('diagnoses', () => items)
const { rows } = paged
</script>

<template>
  <SectionCard
    v-if="items.length"
    heading="inbox-diagnoses"
    title="Coordinator diagnoses"
    :count="items.length"
    description="no reply needed, not counted in the badge"
  >
    <ItemGroup class="gap-3">
      <template v-for="item in rows" :key="`${item.since}-${itemHref(item)}`">
        <InboxRow :item="item" :now="now">
          <p class="text-muted-foreground whitespace-pre-line break-words text-sm">
            {{ item.diagnosis?.text }}
          </p>
        </InboxRow>
      </template>
    </ItemGroup>
    <InboxNav section="diagnoses" label="diagnoses" :paged="paged" />
  </SectionCard>
</template>
