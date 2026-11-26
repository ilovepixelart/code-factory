<script setup lang="ts">
import ContentCard from '../ContentCard.vue'
import SectionCard from '../SectionCard.vue'
import type { InboxItem } from '../../lib/metrics'
import { Item, ItemActions, ItemContent, ItemTitle, ItemGroup } from '@/components/ui/item'
import { itemHref as page, rowId, useInbox, useSectionPage } from './inbox'
import InboxAge from './InboxAge.vue'
import InboxNav from './InboxNav.vue'

// Pull requests ready for review: a queue of links to their tickets, not counted in the badge.
const { items } = defineProps<{ items: InboxItem[] }>()
const { now } = useInbox()
const { paged } = useSectionPage('reviews', () => items)
const { rows } = paged
</script>

<template>
  <SectionCard
    v-if="items.length"
    heading="inbox-reviews"
    title="Ready for review"
    :count="items.length"
    description="a queue, not counted in the badge"
  >
    <ItemGroup class="gap-3">
      <template v-for="item in rows" :key="page(item)">
        <ContentCard :id="rowId('reviews', item)" role="listitem">
          <Item class="py-3">
            <ItemContent>
              <ItemTitle>
                <RouterLink :to="page(item)" class="min-w-0 truncate hover:underline"
                  ><span class="font-mono text-muted-foreground">{{ item.ticket?.id }}</span>
                  {{ item.ticket?.title }}</RouterLink
                >
              </ItemTitle>
            </ItemContent>
            <ItemActions><InboxAge :since="item.since" :now="now" /></ItemActions>
          </Item>
        </ContentCard>
      </template>
    </ItemGroup>
    <InboxNav section="reviews" label="pull requests to review" :paged="paged" />
  </SectionCard>
</template>
