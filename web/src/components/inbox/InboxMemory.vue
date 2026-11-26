<script setup lang="ts">
import ContentCard from '../ContentCard.vue'
import { sentence } from '../../lib/format'
import SectionCard from '../SectionCard.vue'
import { Badge } from '@/components/ui/badge'
import { ref } from 'vue'
import type { InboxItem } from '../../lib/metrics'
import MemoryForm, { type MemoryDraft } from '../MemoryForm.vue'
import { actionKeys, useInbox, useSectionPage } from './inbox'
import { usePressed } from '../../lib/pressed'
import InboxNav from './InboxNav.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { FieldError } from '@/components/ui/field'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemFooter,
  ItemTitle,
  ItemGroup,
} from '@/components/ui/item'

// What agents proposed for the memory store (CF-1168): nothing loads until approved here.
const { items } = defineProps<{ items: InboxItem[] }>()
const { busy, errors, run } = useInbox()
const { press, spins } = usePressed()
const { paged } = useSectionPage('memory', () => items)
const { rows } = paged
const editing = ref('')

const api = (item: InboxItem): string =>
  `/api/memory/${encodeURIComponent(item.memory?.repository ?? '')}/${encodeURIComponent(item.memory?.id ?? '')}`
// Approve or Dismiss: only the one pressed shows its Spinner while the item is sent.
const decide = (item: InboxItem, verdict: 'approve' | 'dismiss') =>
  press(`${verdict} ${actionKeys.memory(item)}`, () =>
    run(actionKeys.memory(item), 'POST', `${api(item)}/${verdict}`),
  )
const deciding = (item: InboxItem, verdict: string): boolean =>
  spins(`${verdict} ${actionKeys.memory(item)}`, busy.value.has(actionKeys.memory(item)))

const draft = (item: InboxItem): MemoryDraft => ({
  kind: item.memory?.kind ?? 'rule',
  statement: item.memory?.statement ?? '',
  why: item.memory?.why ?? '',
  source: item.memory?.source ?? '',
  guard: item.memory?.guard ?? '',
})

async function save(item: InboxItem, changed: MemoryDraft): Promise<void> {
  if (await run(actionKeys.memory(item), 'PATCH', api(item), changed)) editing.value = ''
}
</script>

<template>
  <SectionCard
    v-if="items.length"
    heading="inbox-memory"
    title="Memory proposals"
    :count="items.length"
    description="agents' entries load only once you approve them"
  >
    <ItemGroup class="gap-3">
      <template v-for="item in rows" :key="actionKeys.memory(item)">
        <ContentCard role="listitem">
          <Item class="py-3">
            <ItemContent v-if="editing === actionKeys.memory(item)">
              <MemoryForm
                name="Edit the proposal"
                :start="draft(item)"
                submit="Save"
                :error="errors[actionKeys.memory(item)] ?? ''"
                :busy="busy.has(actionKeys.memory(item))"
                @save="save(item, $event)"
                @cancel="editing = ''"
              />
            </ItemContent>
            <template v-else>
              <ItemContent>
                <ItemTitle class="line-clamp-none wrap-anywhere">{{
                  item.memory?.statement
                }}</ItemTitle>
                <ItemDescription v-if="item.memory?.why" class="line-clamp-none wrap-anywhere"
                  >Why: {{ item.memory.why }}</ItemDescription
                >
                <div
                  class="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
                >
                  <Badge variant="outline">{{ sentence(item.memory?.kind ?? '') }}</Badge>
                  <span>{{ item.memory?.source }}</span>
                  <span>{{ item.memory?.repository }}</span>
                </div>
              </ItemContent>
              <ItemActions>
                <Button
                  type="button"
                  variant="secondary"
                  :disabled="busy.has(actionKeys.memory(item))"
                  @click="decide(item, 'approve')"
                >
                  <Spinner v-if="deciding(item, 'approve')" data-icon="inline-start" />Approve
                </Button>
                <Button type="button" variant="ghost" @click="editing = actionKeys.memory(item)">
                  Edit
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  :disabled="busy.has(actionKeys.memory(item))"
                  @click="decide(item, 'dismiss')"
                >
                  <Spinner v-if="deciding(item, 'dismiss')" data-icon="inline-start" />Dismiss
                </Button>
              </ItemActions>
              <ItemFooter v-if="errors[actionKeys.memory(item)]">
                <FieldError>{{ errors[actionKeys.memory(item)] }}</FieldError>
              </ItemFooter>
            </template>
          </Item>
        </ContentCard>
      </template>
    </ItemGroup>
    <InboxNav section="memory" label="memory proposals" :paged="paged" />
  </SectionCard>
</template>
