<script setup lang="ts">
import ContentCard from '../ContentCard.vue'
import SectionCard from '../SectionCard.vue'
import { short } from '../../lib/format'
import type { InboxItem } from '../../lib/metrics'
import { ticketHref } from '../../lib/ticket'
import { rowId, useInbox, useSectionPage } from './inbox'
import InboxAge from './InboxAge.vue'
import InboxNav from './InboxNav.vue'
import StackTrace from '../ai/StackTrace/StackTrace.vue'
import { Button } from '@/components/ui/button'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemFooter,
  ItemGroup,
} from '@/components/ui/item'

// A default branch whose own run failed (CF-1251): the step, the commit and the log's last lines
// as a stack trace, the merge the search named. Nothing waits on it; it leaves once a run passes.
const { items } = defineProps<{ items: InboxItem[] }>()
const { now, primary } = useInbox()
const { paged, offset } = useSectionPage('main', () => items)
const { rows } = paged
</script>

<template>
  <SectionCard
    v-if="items.length"
    heading="inbox-main"
    title="Failing main"
    :count="items.length"
    description="the default branch's own run failed; nothing waits on it"
  >
    <ItemGroup class="gap-3">
      <template v-for="(item, n) in rows" :key="item.main?.repository ?? n">
        <ContentCard :id="rowId('main', item)" role="listitem">
          <Item class="py-3">
            <ItemContent>
              <StackTrace
                :error="`${item.main?.repository}: ${item.main?.step || 'the run'} ${item.main?.reason || 'failed'} at ${short(item.main?.commit ?? '')}`"
                :frames="item.main?.tail ? item.main.tail.split('\n') : []"
                label="Last lines of the log"
              />
            </ItemContent>
            <ItemActions><InboxAge :since="item.since" :now="now" /></ItemActions>
            <ItemFooter>
              <ItemDescription class="flex min-w-0 flex-wrap items-center gap-2">
                <span v-if="item.main?.broken_by"
                  >Broken by merge
                  <span class="font-mono">{{ short(item.main.broken_by) }}</span></span
                >
                <span class="font-mono min-w-0 break-all">{{ item.main?.log }}</span>
              </ItemDescription>
              <Button v-if="item.main?.ticket" as-child :variant="primary('main', offset + n)"
                ><RouterLink :to="ticketHref(item.main.repository, item.main.ticket)"
                  >Open {{ item.main.ticket }}</RouterLink
                ></Button
              >
            </ItemFooter>
          </Item>
        </ContentCard>
      </template>
    </ItemGroup>
    <InboxNav section="main" label="failing branches" :paged="paged" />
  </SectionCard>
</template>
