<script setup lang="ts">
import { computed, useTemplateRef } from 'vue'
import type { InboxItem } from '../../lib/metrics'
import { answerBody } from '../../lib/questions'
import QuestionAsk from '../QuestionAsk.vue'
import { itemHref, questionKey, ticketApi, useInbox } from './inbox'
import { FieldError } from '@/components/ui/field'

// One open question in the Inbox: the shared question (QuestionAsk), sent to its ticket from here.
// What is typed or ticked survives each refresh, as this stays mounted under its key.
const { item, index } = defineProps<{ item: InboxItem; index: number }>()
const { busy, errors, run, primary } = useInbox()

const key = computed(() => questionKey(item))
const asked = computed(() => item.question)
const waiting = computed(() => busy.value.has(key.value))
const question = useTemplateRef<InstanceType<typeof QuestionAsk>>('question')

async function send(given: { choices: string[] } | { answer: string }): Promise<void> {
  // `run` marks the question busy as it starts, so a second press before it ends sends nothing.
  if (waiting.value) return
  if (await run(key.value, 'POST', `${ticketApi(item)}/answers`, answerBody(asked.value, given))) {
    question.value?.clear()
  }
}
</script>

<template>
  <article
    :id="key"
    :data-inbox-item="asked?.text"
    :data-href="itemHref(item)"
    tabindex="-1"
    class="grid grid-cols-1 gap-2 rounded-md py-3 outline-none first:pt-0 last:pb-0 focus-visible:ring-3 focus-visible:ring-ring/50"
  >
    <QuestionAsk
      v-if="asked"
      ref="question"
      :asked="asked"
      :waiting="waiting"
      :lead="primary('questions', index)"
      @send="send($event)"
    />
    <FieldError v-if="errors[key]">{{ errors[key] }}</FieldError>
  </article>
</template>
