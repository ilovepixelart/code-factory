<script setup lang="ts">
import SectionHeading from './ticket/SectionHeading.vue'
import { Archive02Icon, Delete02Icon, PlusSignIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed, inject, nextTick, provide, reactive, ref, useTemplateRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useTicketKeys } from '../lib/ticketKeys'
import { act } from '../lib/actions'
import { confirm } from '../lib/confirm'
import { BOARD } from '../lib/live'
import { perform, refusalText, refused } from '../lib/notice'
import { vRendered } from '../lib/rendered'
import { dropBlankTitle, fieldsOf, type TicketView } from '../lib/ticket'
import { useTicketRead } from './ticket/read'
import { setArchived } from '../lib/ticketActions'
import { SECTION_LEVEL, TICKET_FORM, useTicketTasks } from './ticket/context'
import TicketActivity from './ticket/TicketActivity.vue'
import NewTicket from './NewTicket.vue'
import TicketAgent from './ticket/TicketAgent.vue'
import TicketDocuments from './ticket/TicketDocuments.vue'
import TicketEvidence from './ticket/TicketEvidence.vue'
import TicketFindings from './ticket/TicketFindings.vue'
import TicketLinks from './ticket/TicketLinks.vue'
import TicketPlan from './ticket/TicketPlan.vue'
import SaveStatus from './ticket/SaveStatus.vue'
import TicketProperties from './ticket/TicketProperties.vue'
import TicketQuestions from './ticket/TicketQuestions.vue'
import TicketScreens from './ticket/TicketScreens.vue'
import TicketStatus from './ticket/TicketStatus.vue'
import TicketTitle from './ticket/TicketTitle.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import ReadState from './ReadState.vue'
import { Empty, EmptyDescription, EmptyHeader } from '@/components/ui/empty'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'

// One form for the panel and the page: every field
// saves itself when changed; comments, answers, archive and delete are
// sent from it. Agent and checks controls come with CF-210.
const { repository, id, page } = defineProps<{
  repository: string
  id: string
  page?: boolean
}>()
const emit = defineEmits<{ close: []; missing: []; loaded: [view: TicketView] }>()
defineSlots<{ default?: () => unknown }>()
// The page sits inside its own gutter; the panel has none.
const inset = computed(() => (page ? 'page-wide' : 'px-4 py-6 md:px-6'))

const live = inject(BOARD)
live?.follow()
const child = useTemplateRef<InstanceType<typeof NewTicket>>('child')
const router = useRouter()
const view = ref<TicketView | null>(null)
const model = reactive(fieldsOf({}))
// The ticket's fields as the form loaded or last saved them: a save sends what differs.
const loaded = reactive(fieldsOf({}))
const saved = ref('')
const failed = ref('')
const errors = ref<Partial<Record<string, string>>>({})
const now = ref(Date.now() / 1000)
const base = computed(
  () => `/api/tickets/${encodeURIComponent(repository)}/${encodeURIComponent(id)}`,
)

const {
  read: ticketRead,
  load,
  opening,
} = useTicketRead(
  () => repository,
  () => id,
  () => (view.value?.runs.length ?? 0) > 0,
)
watch(
  () => [repository, id],
  () => (saved.value = ''),
)
// Once the ticket is shown it stands until the next read.
watch([ticketRead.error, view], () => {
  failed.value = ticketRead.error.value && !view.value ? refusalText(ticketRead.error.value) : ''
})
watch(
  ticketRead.dataUpdatedAt,
  (at) => {
    if (!ticketRead.isSuccess.value) return
    const fresh = ticketRead.data.value ?? null
    now.value = Date.now() / 1000
    if (!fresh) {
      emit('missing')
      view.value = null
      return
    }
    view.value = fresh
    emit('loaded', fresh)
    if (opening(at)) {
      Object.assign(model, fieldsOf(fresh.ticket))
      Object.assign(loaded, fieldsOf(fresh.ticket))
    }
  },
  { immediate: true },
)
// The views of the ticket follow the board; the fields keep what is being typed.
watch(
  () => live?.board.value,
  () => void load(),
)

// The fields keep what is typed: a save refreshes the views of the ticket, not its fields, so a
// field being typed in while another saves is not overwritten.
const refresh = async (): Promise<void> => {
  await Promise.all([load(), live?.refresh()])
}

defineExpose({ refresh })

async function save(field?: string): Promise<void> {
  const changed = fieldsOf(model, loaded)
  const blank = dropBlankTitle(changed)
  if (blank) model.title = loaded.title
  try {
    if (Object.keys(changed).length) await act('PATCH', base.value, changed)
    Object.assign(loaded, changed)
    errors.value = blank ? { title: 'A ticket needs a title.' } : {}
    saved.value = blank ? 'Not saved' : 'Saved'
  } catch (error) {
    saved.value = 'Not saved'
    // Under the field just changed when it was sent, else the first one sent.
    const where = field && field in changed ? field : Object.keys(changed)[0]
    errors.value = where ? { [where]: refusalText(error) } : {}
    refused(error)
  }
  await refresh()
}

const tasks = useTicketTasks(base, refresh)
const { busy, press, spins } = tasks
provide(TICKET_FORM, { model, save, errors, base, refresh, ...tasks })
const sectionLevel = computed(() => (page ? 2 : 3))
provide(SECTION_LEVEL, sectionLevel)

async function archive(): Promise<void> {
  busy.value = true
  const changed = fieldsOf(model, loaded)
  const done = await perform(
    () => setArchived(base.value, !view.value?.ticket.archived, changed),
    refresh,
  )
  if (done) Object.assign(loaded, changed)
  busy.value = false
  if (done && !page) emit('close')
}

async function remove(): Promise<void> {
  if (!(await confirm(`${id} ${String(view.value?.ticket.title ?? '')}`))) return
  busy.value = true
  const done = await perform(
    () => act('DELETE', base.value),
    async () => {
      await live?.refresh()
    },
  )
  busy.value = false
  if (!done) return
  if (page) await router.push('/tickets')
  else emit('close')
}

const ticket = computed(() => view.value?.ticket ?? {})
const labelledUi = computed(() =>
  String(ticket.value.labels ?? '')
    .split(',')
    .some((l) => l.trim() === 'ui'),
)

// The Parent and Blocked by properties follow a link change unless they are being edited.
function followLinks(): void {
  for (const field of ['parent', 'blocked_by'] as const) {
    const fresh = String(view.value?.ticket[field] ?? '')
    if (model[field] === loaded[field]) model[field] = fresh
    loaded[field] = fresh
  }
}
const written = computed(() => String(ticket.value.description ?? '').trim() !== '')
// The description opens on its rendering once written, on the field while empty.
const descriptionTab = ref<string | number>('write')
watch(
  written,
  (now) => {
    descriptionTab.value = now ? 'preview' : 'write'
  },
  { immediate: true },
)

// The ticket's own keys (s, r, e) press its controls, on the page and in the panel.
useTicketKeys(useTemplateRef<HTMLFormElement>('ticketForm'))
</script>

<template>
  <form
    v-if="view"
    ref="ticketForm"
    class="flex flex-col"
    :class="page ? 'min-h-full' : 'min-h-0 flex-1'"
    :aria-label="`Edit ticket ${id}`"
    @submit.prevent
  >
    <div class="@container flex-1" :class="{ 'min-h-0 overflow-y-auto': !page }">
      <div class="grid min-h-full @3xl:grid-cols-[minmax(0,1fr)_260px]">
        <div class="grid min-w-0 grid-cols-1 content-start gap-6" :class="inset">
          <div class="grid gap-3 border-b pb-5">
            <TicketTitle :id="id" />
            <TicketStatus :view="view" />
          </div>
          <TicketQuestions v-if="view.questions.length" :view="view" />
          <TicketPlan v-if="view.plan" :plan="view.plan" />
          <TicketFindings :id="id" :repository="repository" />
          <section aria-labelledby="description-heading">
            <SectionHeading id="description-heading" class="mb-2"> Description </SectionHeading>
            <Tabs v-model="descriptionTab">
              <TabsList aria-label="Description view">
                <TabsTrigger value="write">Write</TabsTrigger>
                <TabsTrigger value="preview">Preview</TabsTrigger>
              </TabsList>
              <TabsContent value="preview" class="mt-2">
                <div
                  v-if="written"
                  v-rendered:[sectionLevel+1]="view.description_html"
                  class="typeset typeset-doc"
                ></div>
                <Empty v-else>
                  <EmptyHeader>
                    <EmptyDescription>Nothing written yet.</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              </TabsContent>
              <TabsContent value="write" class="mt-2">
                <Textarea
                  :model-value="model.description"
                  name="description"
                  rows="8"
                  aria-label="Description"
                  placeholder="What and why. Markdown; lines starting with - [ ] count as a checklist."
                  @update:model-value="model.description = String($event)"
                  @change="nextTick(save)"
                />
              </TabsContent>
            </Tabs>
          </section>
          <TicketAgent :view="view" :now="now" />
          <TicketEvidence :view="view" />
          <TicketActivity :view="view" :now="now" />
          <TicketDocuments :id="id" :repository="repository" :view="view" />
          <TicketScreens v-if="labelledUi" :id="id" :repository="repository" :view="view" />
          <TicketLinks :id="id" :repository="repository" :view="view" @changed="followLinks()" />
        </div>
        <TicketProperties :id="id" :view="view" />
      </div>
      <slot />
    </div>
    <footer
      data-testid="ticket-footer"
      class="flex items-center gap-2 border-t border-border bg-background px-4 py-3"
      :class="{ 'sticky bottom-0': page }"
    >
      <Button
        type="button"
        variant="ghost"
        class="gap-1.5"
        @click="child?.open({ repository, parent: id })"
      >
        <HugeiconsIcon :icon="PlusSignIcon" data-icon="inline-start" aria-hidden="true" />New child
        ticket
      </Button>
      <Button
        type="button"
        variant="ghost"
        class="gap-1.5"
        :disabled="busy"
        @click="press('archive', archive)"
      >
        <Spinner v-if="spins('archive', busy)" data-icon="inline-start" />
        <HugeiconsIcon v-else :icon="Archive02Icon" data-icon="inline-start" aria-hidden="true" />{{
          ticket.archived ? 'Restore' : 'Archive'
        }}
      </Button>
      <Button
        type="button"
        variant="destructive"
        class="gap-1.5"
        :disabled="busy"
        @click="press('delete', remove)"
      >
        <Spinner v-if="spins('delete', busy)" data-icon="inline-start" />
        <HugeiconsIcon
          v-else
          :icon="Delete02Icon"
          data-icon="inline-start"
          aria-hidden="true"
        />Delete
      </Button>
      <SaveStatus :saved="saved" />
    </footer>
    <NewTicket ref="child" prefix="child" />
  </form>
  <ReadState v-else :class="inset" what="the ticket" :failed="failed" @retry="void load()" />
</template>
