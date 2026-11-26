<script setup lang="ts">
import { Card, CardContent } from '@/components/ui/card'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { act, ask, Refused } from '../lib/actions'
import { span } from '../lib/format'
import {
  NOTHING_PICKED,
  ready,
  reply,
  type Asked as Question,
  type Picking,
} from '../lib/questions'
import QuestionChoices from '../components/QuestionChoices.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { usePressed } from '../lib/pressed'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Textarea } from '@/components/ui/textarea'

// What a pushed permission request's or question's reply link opens, without the sign-in (CF-760,
// CF-997): the one item, read on load, and answered only when a button is pressed, since link
// scanners and notification previews fetch links.
interface Asked {
  ticket: string
  title: string
  tool: string
  summary: string
  at: number
}
interface AskedQuestion extends Question {
  kind: 'question'
  ticket: string
  title: string
}

const path = `/api/reply/${String(useRoute().params.token)}`
const asked = ref<Asked | AskedQuestion | null>(null)
const question = computed(() => (asked.value && 'kind' in asked.value ? asked.value : null))
const permission = computed(() => (asked.value && !('kind' in asked.value) ? asked.value : null))
const picking = ref<Picking>(NOTHING_PICKED)
const written = ref('')
const canSend = computed(() =>
  question.value?.choices.length ? ready(picking.value) : written.value.trim() !== '',
)
const said = ref('')
const refusal = ref('')
const answerError = ref('')
const sending = ref(false)
const { press: pressing, spins } = usePressed()

function refuse(error: unknown): void {
  asked.value = null
  refusal.value = error instanceof Refused ? error.message : 'The board did not answer.'
}

onMounted(async () => {
  try {
    asked.value = await ask<Asked | AskedQuestion>(path)
  } catch (error) {
    refuse(error)
  }
})

async function press(verdict: 'allow' | 'deny'): Promise<void> {
  sending.value = true
  try {
    said.value = (await act('POST', path, { verdict })).notice
  } catch (error) {
    refuse(error)
  } finally {
    sending.value = false
  }
}

async function answer(): Promise<void> {
  if (sending.value || !canSend.value) return
  sending.value = true
  answerError.value = ''
  try {
    const sent = question.value?.choices.length ? reply(picking.value) : { answer: written.value }
    said.value = (await act('POST', path, sent)).notice
  } catch (error) {
    answerError.value = error instanceof Refused ? error.message : 'The board did not answer.'
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <main class="page-wide">
    <section class="mx-auto max-w-2xl">
      <Card
        ><CardContent class="grid gap-4 text-sm">
          <h1 class="cn-font-heading text-lg font-semibold">
            {{ question ? 'Question' : 'Permission request' }}
          </h1>
          <FieldError v-if="refusal">{{ refusal }}</FieldError>
          <template v-else-if="asked">
            <p class="break-words">
              <span class="font-mono text-sm">{{ asked.ticket }}</span
              >&#32;{{ asked.title }}
            </p>
            <p v-if="said" class="font-medium">{{ said }}</p>
            <template v-else-if="question">
              <p class="break-words font-medium">{{ question.text }}</p>
              <QuestionChoices
                v-if="question.choices.length"
                v-model="picking"
                :question="question"
                @enter="answer()"
              />
              <Field v-else>
                <FieldLabel for="reply-answer">Your answer</FieldLabel>
                <Textarea
                  id="reply-answer"
                  :model-value="written"
                  rows="3"
                  @update:model-value="written = String($event)"
                />
              </Field>
              <FieldError v-if="answerError" role="alert">{{ answerError }}</FieldError>
              <div class="flex justify-end">
                <Button type="button" :disabled="sending || !canSend" @click="answer()">
                  <Spinner v-if="sending" data-icon="inline-start" />Send
                </Button>
              </div>
            </template>
            <template v-else-if="permission">
              <p class="break-words">
                <span class="font-mono text-sm">{{ permission.tool }}</span
                >&#32;<span class="font-mono text-sm">{{ permission.summary }}</span>
              </p>
              <p class="text-muted-foreground text-sm">
                asked {{ span(Date.now() / 1000 - permission.at) }} ago
              </p>
              <div class="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  :disabled="sending"
                  @click="pressing('deny', () => press('deny'))"
                >
                  <Spinner v-if="spins('deny', sending)" data-icon="inline-start" />Deny
                </Button>
                <Button
                  type="button"
                  :disabled="sending"
                  @click="pressing('allow', () => press('allow'))"
                  ><Spinner v-if="spins('allow', sending)" data-icon="inline-start" />Allow</Button
                >
              </div>
            </template>
          </template>
        </CardContent></Card
      >
    </section>
  </main>
</template>
