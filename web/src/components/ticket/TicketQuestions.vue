<script setup lang="ts">
import SectionHeading from './SectionHeading.vue'
import { computed, reactive } from 'vue'
import type { TicketView } from '../../lib/ticket'
import QuestionAsk from '../QuestionAsk.vue'
import { useTicketForm } from './context'

// The questions of the ticket's documents, each the shared question (QuestionAsk) the Inbox shows,
// answered from here; an answered one shows its answer and takes a new one, which replaces it.
const { view } = defineProps<{ view: TicketView }>()

type Question = TicketView['questions'][number]

const { busy, send, press } = useTicketForm()
const asks = reactive<Record<string, { clear: () => void } | null>>({})
const waiting = computed(() => view.questions.filter((q) => !q.answer).length)
const keyOf = (q: Question): string => `${q.document}-${String(q.index)}`

async function answer(
  q: Question,
  given: { choices: string[] } | { answer: string },
): Promise<void> {
  // The form's busy state is set as a send starts, so a second Enter before it ends sends nothing.
  if (busy.value) return
  const edit = q.answer ? { replace: true } : {}
  if (
    await send('answers', {
      document: q.document,
      index: q.index,
      question: q.text,
      ...given,
      ...edit,
    })
  ) {
    asks[keyOf(q)]?.clear()
  }
}
</script>

<template>
  <section aria-labelledby="questions-heading">
    <SectionHeading id="questions-heading" class="mb-3"
      >Open questions
      <span class="text-muted-foreground font-normal">{{ waiting }} waiting</span>
    </SectionHeading>
    <ul aria-label="Open questions" class="grid gap-6">
      <li v-for="q in view.questions" :key="keyOf(q)">
        <QuestionAsk
          :ref="(el) => (asks[keyOf(q)] = el as { clear: () => void } | null)"
          :asked="q"
          :waiting="busy"
          :answer="q.answer"
          :answered-by="q.answered_by"
          @send="press(keyOf(q), () => answer(q, $event))"
        />
      </li>
    </ul>
  </section>
</template>
