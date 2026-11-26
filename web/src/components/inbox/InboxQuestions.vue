<script setup lang="ts">
import ContentCard from '../ContentCard.vue'
import SectionCard from '../SectionCard.vue'
import { computed } from 'vue'
import type { InboxItem } from '../../lib/metrics'
import { itemHref, questionKey, rowId, useInbox, useSectionPage } from './inbox'
import InboxAge from './InboxAge.vue'
import InboxAsk from './InboxAsk.vue'
import InboxNav from './InboxNav.vue'
import InboxTicketLink from './InboxTicketLink.vue'
import { Item, ItemContent, ItemHeader, ItemGroup } from '@/components/ui/item'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { ref } from 'vue'
import { answerBody, recommendedOf } from '../../lib/questions'
import { ticketApi } from './inbox'

// Questions an agent waits on, one card per ticket holding the questions of it on this page,
// each answered in place; the card is as old as its longest wait. Every question that recommends
// one choice can be answered with it in one go, after a confirm listing what is sent: an answer
// reaches its agent at once, so there is nothing to undo.
const { items } = defineProps<{ items: InboxItem[] }>()
const { now, run } = useInbox()
const batch = computed(() =>
  items.flatMap((item) => {
    const choice = recommendedOf(item.question)
    return choice === null ? [] : [{ item, choice }]
  }),
)
const confirming = ref(false)

async function acceptAll(): Promise<void> {
  confirming.value = false
  for (const { item, choice } of batch.value) {
    const body = answerBody(item.question, { choices: [choice] })
    await run(questionKey(item), 'POST', `${ticketApi(item)}/answers`, body)
  }
}
const { paged, offset } = useSectionPage('questions', () => items)
const { rows } = paged

interface Card {
  first: InboxItem
  since: number | null
  asked: { item: InboxItem; index: number }[]
}

const cards = computed(() => {
  const byTicket = new Map<string, Card>()
  rows.value.forEach((item, n) => {
    const key = itemHref(item)
    const card = byTicket.get(key) ?? { first: item, since: null, asked: [] }
    card.asked.push({ item, index: offset.value + n })
    if (item.since !== null) card.since = Math.min(card.since ?? item.since, item.since)
    byTicket.set(key, card)
  })
  return [...byTicket.values()]
})
</script>

<template>
  <SectionCard
    v-if="items.length"
    heading="inbox-questions"
    title="Questions"
    :count="items.length"
    description="an agent waits for your answer"
  >
    <template v-if="batch.length" #action>
      <Button type="button" variant="outline" @click="confirming = true"
        >Accept {{ batch.length }} recommended</Button
      >
    </template>
    <AlertDialog v-model:open="confirming">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Send {{ batch.length }} recommended answers</AlertDialogTitle>
          <AlertDialogDescription
            >Each answer reaches its agent at once and cannot be undone.</AlertDialogDescription
          >
        </AlertDialogHeader>
        <dl class="grid grid-cols-1 gap-2 text-sm">
          <div v-for="entry in batch" :key="questionKey(entry.item)">
            <dt class="text-muted-foreground wrap-anywhere">
              <span class="font-mono">{{ entry.item.ticket?.id }}</span>
              {{ entry.item.question?.text }}
            </dt>
            <dd class="font-medium wrap-anywhere">{{ entry.choice }}</dd>
          </div>
        </dl>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction @click="acceptAll()"
            >Send {{ batch.length }} answers</AlertDialogAction
          >
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    <ItemGroup>
      <ContentCard
        v-for="card in cards"
        :id="rowId('questions', card.first)"
        :key="itemHref(card.first)"
        role="listitem"
      >
        <Item class="py-3">
          <ItemHeader>
            <InboxTicketLink :item="card.first" /><InboxAge :since="card.since" :now="now" />
          </ItemHeader>
          <ItemContent class="min-w-0">
            <InboxAsk
              v-for="entry in card.asked"
              :key="questionKey(entry.item)"
              :item="entry.item"
              :index="entry.index"
            />
          </ItemContent>
        </Item>
      </ContentCard>
    </ItemGroup>
    <InboxNav section="questions" label="questions" :paged="paged" />
  </SectionCard>
</template>
