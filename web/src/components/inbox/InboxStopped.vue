<script setup lang="ts">
import SectionCard from '../SectionCard.vue'
import { ItemGroup } from '@/components/ui/item'
import { PlayIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import type { InboxItem } from '../../lib/metrics'
import { actionKeys, itemHref as page, rowId, ticketApi, useInbox, useSectionPage } from './inbox'
import InboxNav from './InboxNav.vue'
import InboxRow from './InboxRow.vue'
import { haltWords } from '../../lib/format'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'

// Agents stopped on a ticket, each restarted in place.
const { items } = defineProps<{ items: InboxItem[] }>()
const { now, busy, errors, run, primary } = useInbox()
const { paged, offset } = useSectionPage('stopped', () => items)
const { rows } = paged
</script>

<template>
  <SectionCard
    v-if="items.length"
    heading="inbox-stopped"
    title="Stopped agents"
    :count="items.length"
    description="restart the agent, or open the ticket to see why"
  >
    <ItemGroup class="gap-3">
      <template v-for="(item, n) in rows" :key="page(item)">
        <InboxRow
          :id="rowId('stopped', item)"
          :item="item"
          :now="now"
          :error="errors[actionKeys.stopped(item)] ?? ''"
          wrap
        >
          <template #actions>
            <span class="flex gap-2">
              <Button as-child variant="ghost"
                ><RouterLink :to="page(item)">Open ticket</RouterLink></Button
              >
              <Button
                type="button"
                :variant="primary('stopped', offset + n)"
                class="gap-1.5"
                :disabled="busy.has(actionKeys.stopped(item))"
                @click="
                  run(actionKeys.stopped(item), 'POST', `${ticketApi(item)}/runs`, {
                    permissions: 'bypassPermissions',
                    loop: true,
                  })
                "
              >
                <Spinner v-if="busy.has(actionKeys.stopped(item))" data-icon="inline-start" />
                <HugeiconsIcon
                  v-else
                  :icon="PlayIcon"
                  data-icon="inline-start"
                  aria-hidden="true"
                />Restart agent
              </Button>
            </span>
          </template>
          <p class="min-w-0 break-words text-sm text-muted-foreground">
            {{ haltWords(item.reason) }}
          </p>
        </InboxRow>
      </template>
    </ItemGroup>
    <InboxNav section="stopped" label="stopped agents" :paged="paged" />
  </SectionCard>
</template>
