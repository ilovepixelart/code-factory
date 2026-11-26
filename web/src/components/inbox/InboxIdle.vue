<script setup lang="ts">
import type { InboxItem } from '../../lib/metrics'
import SectionCard from '../SectionCard.vue'
import InboxNav from './InboxNav.vue'
import InboxRow from './InboxRow.vue'
import { itemHref, rowId, useInbox, useSectionPage } from './inbox'
import { Button } from '@/components/ui/button'
import { ItemGroup } from '@/components/ui/item'

const { items } = defineProps<{ items: InboxItem[] }>()
const { now, primary } = useInbox()
const { paged, offset } = useSectionPage('idle', () => items)
const { rows } = paged
</script>

<template>
  <SectionCard
    v-if="items.length"
    heading="inbox-idle"
    title="Idle pull requests"
    :count="items.length"
    description="Open pull requests with no GitHub update for at least two days"
  >
    <ItemGroup class="gap-3">
      <template v-for="(item, index) in rows" :key="itemHref(item)">
        <InboxRow :id="rowId('idle', item)" :item="item" :now="now">
          <template #actions>
            <Button as-child :variant="primary('idle', offset + index)"
              ><a :href="item.reason">Open pull request</a></Button
            >
          </template>
        </InboxRow>
      </template>
    </ItemGroup>
    <InboxNav section="idle" label="idle pull requests" :paged="paged" />
  </SectionCard>
</template>
