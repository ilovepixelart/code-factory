<script setup lang="ts">
import ContentCard from '../ContentCard.vue'
import SectionCard from '../SectionCard.vue'
import { short, trim, withoutTrailingSlashes } from '../../lib/format'
import type { InboxItem } from '../../lib/metrics'
import { rowId, useInbox, useSectionPage } from './inbox'
import InboxAge from './InboxAge.vue'
import InboxNav from './InboxNav.vue'
import { Button } from '@/components/ui/button'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
  ItemGroup,
} from '@/components/ui/item'

// Sessions that wait for a permission in their own terminal: the Inbox cannot answer them, so
// they only open the session.
const { items } = defineProps<{ items: InboxItem[] }>()
const { now, primary } = useInbox()
const { paged, offset } = useSectionPage('sessions', () => items)
const { rows } = paged

const place = (cwd: string): string => {
  const name = withoutTrailingSlashes(cwd).split('/').at(-1) ?? ''
  return name === '' ? cwd : name
}
</script>

<template>
  <SectionCard
    v-if="items.length"
    heading="inbox-sessions"
    title="Waiting sessions"
    :count="items.length"
    description="approve or deny in the agent's terminal"
  >
    <ItemGroup class="gap-3">
      <template v-for="(item, n) in rows" :key="item.session?.session_id ?? n">
        <ContentCard :id="rowId('sessions', item)" role="listitem">
          <Item class="py-3">
            <ItemContent>
              <ItemTitle class="line-clamp-none wrap-anywhere">
                Waits for permission<template v-if="item.session?.action"
                  >:
                  <span class="font-mono"
                    >{{ item.session.action.tool }}
                    {{ trim(item.session.action.summary, 80) }}</span
                  ></template
                >
              </ItemTitle>
              <ItemDescription class="flex flex-wrap items-center gap-2">
                <span>{{ place(item.session?.cwd ?? '') }}</span
                ><span class="font-mono">{{ short(item.session?.session_id ?? '') }}</span>
              </ItemDescription>
            </ItemContent>
            <ItemActions>
              <InboxAge :since="item.since" :now="now" />
              <Button as-child :variant="primary('sessions', offset + n)"
                ><RouterLink :to="`/sessions/${item.session?.session_id}`"
                  >Open session</RouterLink
                ></Button
              >
            </ItemActions>
          </Item>
        </ContentCard>
      </template>
    </ItemGroup>
    <InboxNav section="sessions" label="waiting sessions" :paged="paged" />
  </SectionCard>
</template>
