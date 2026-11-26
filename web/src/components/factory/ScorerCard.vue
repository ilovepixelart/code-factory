<script setup lang="ts">
import ContentCard from '../ContentCard.vue'
import { share, windowWords, type ScorerCard } from '../../lib/factory'
import { rate } from '../../lib/scorers'
import { Item, ItemActions, ItemContent, ItemDescription, ItemTitle } from '@/components/ui/item'

// One scorer's results in the range: its question, the pass rate (yes over yes and no) as a whole
// percent, how many answers it gave over which window and, when it has one, the average score
// (0 to 1) as a whole percent.
// `detail` adds the yes, no and unclear counts the rate is made of.
const { card, detail, repository } = defineProps<{
  card: ScorerCard
  detail?: boolean
  /** Name the scorer's repository: when the cards span more than one. */
  repository?: boolean
}>()
</script>

<template>
  <ContentCard data-scorer role="listitem">
    <Item class="items-start py-3">
      <ItemContent class="min-w-0">
        <ItemTitle class="font-mono wrap-anywhere">{{ card.name }}</ItemTitle>
        <ItemDescription v-if="repository" data-repository class="wrap-anywhere">{{
          card.repository
        }}</ItemDescription>
        <ItemDescription class="wrap-anywhere">{{ card.question }}</ItemDescription>
        <div class="flex flex-col gap-0.5 text-muted-foreground">
          <p>
            {{ card.asked }} {{ card.asked === 1 ? 'answer' : 'answers' }},
            {{ windowWords(card.window) }}
          </p>
          <p v-if="detail" data-counts>
            {{ card.yes }} yes, {{ card.no }} no, {{ card.unclear }} unclear
          </p>
          <p v-if="card.average_score !== null" data-average>
            average score {{ share(card.average_score, 1) }}
          </p>
        </div>
      </ItemContent>
      <ItemActions>
        <p class="text-2xl font-semibold tabular-nums">{{ rate(card) }}</p>
      </ItemActions>
    </Item>
  </ContentCard>
</template>
