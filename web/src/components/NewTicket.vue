<script setup lang="ts">
import { Field as VeeField, useForm } from 'vee-validate'
import { inject, nextTick, reactive, ref, useTemplateRef, watch } from 'vue'
import { routerKey } from 'vue-router'
import { latest } from '../lib/latest'
import { loadText, saveText } from '../lib/storage'
import { ticketHref } from '../lib/ticket'
import { BOARD } from '../lib/live'
import { announce, useAction } from '../lib/notice'
import { useOverlay } from '../lib/overlayHistory'
import { readJson } from '../lib/actions'
import { followTemplate, templateFor } from '../lib/templates'
import PropertyGroups from './ticket/PropertyGroups.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'

// The new ticket dialog (shadcn-vue's Dialog, a focused task that takes input): its title, its
// description, then where it goes and what it is (Repository, Type, Priority, Labels) with the rest
// folded under More properties. The description follows the type's template until the person writes
// in it. The title is the one
// field checked before sending (VeeValidate); the board refuses the rest.
// The fields' ids start with `prefix`, so a second sheet in the page (a ticket's child sheet)
// never repeats the board's.
const { prefix = 'new' } = defineProps<{ prefix?: string }>()
const live = inject(BOARD)
const router = inject(routerKey, null)
// The repository the last ticket went to, per browser, chosen first next time.
const LAST_REPOSITORY = 'codeFactoryLastRepository'
const open = useOverlay()
const title = useTemplateRef<InstanceType<typeof Input>>('title')
const focusField = (): void => (title.value?.$el as HTMLInputElement | undefined)?.focus()
const repositories = ref<string[]>([])
const { busy, error, send } = useAction()
const { handleSubmit, resetForm, setFieldError, values } = useForm<{ title: string }>({
  validationSchema: {
    title: (value: unknown) =>
      (typeof value === 'string' && value.trim() !== '') || 'Give the ticket a title',
  },
  initialValues: { title: '' },
  // The dialog unmounts its content while closed; a dismissed draft keeps its title.
  keepValuesOnUnmount: true,
})
const blank = () => ({
  repository: '',
  description: '',
  type: 'feature',
  priority: '',
  due: '',
  labels: '',
  assignee: '',
  blocked: '',
  parent: '',
  blocked_by: '',
  budget: '',
  branch: '',
  tests: '',
  e2e: '',
  pages: '',
  caused_by: '',
  parallel: '',
  source: '',
})
const ticket = reactive(blank())
let lastTemplate = ''
// The preset the form was last opened for: a form dismissed and opened again for the same one
// keeps its text, any other starts blank.
let openedFor: string | null = null
const opens = latest()
const templates = latest()

async function loadTemplate(): Promise<void> {
  if (!ticket.repository) return
  const asked = { repository: ticket.repository, type: ticket.type }
  const current = templates.take()
  // A template the board does not answer leaves the description as it is.
  const template = await templateFor(asked.repository, asked.type).catch(() => null)
  if (template === null || !current()) return
  if (asked.repository !== ticket.repository || asked.type !== ticket.type) return
  ticket.description = followTemplate(ticket.description, lastTemplate, template)
  if (ticket.description === template) lastTemplate = template
}
watch(
  () => [ticket.repository, ticket.type],
  () => void loadTemplate(),
)

/** Open a blank form, or one for a child (CF-817): `parent` fills Parent, and `repository` is
 *  chosen when the board lists it, else the first listed. A form closed without Create or Cancel
 *  and opened again for the same preset keeps what was typed. */
async function show(preset: { repository?: string; parent?: string } = {}): Promise<void> {
  const current = opens.take()
  const key = `${preset.repository ?? ''}|${preset.parent ?? ''}`
  const kept = !open.value && openedFor === key
  openedFor = key
  if (!kept) discard(preset.parent)
  error.value = ''
  setFieldError('title', undefined)
  open.value = true
  // A read the board does not answer, or answers with anything but a list, leaves the list empty
  // and the form open.
  repositories.value = []
  const listed = await readJson<string[]>('/api/repositories').catch(() => null)
  if (!current()) return
  repositories.value = Array.isArray(listed) ? listed : []
  // The preset's repository, else the one the last ticket went to, else the first listed.
  const asked = preset.repository ?? loadText(LAST_REPOSITORY) ?? ''
  if (!repositories.value.includes(ticket.repository)) {
    ticket.repository = repositories.value.includes(asked) ? asked : (repositories.value[0] ?? '')
  }
}

function discard(parent = ''): void {
  Object.assign(ticket, blank(), { parent })
  resetForm({ values: { title: '' } })
  lastTemplate = ''
}

function close(): void {
  open.value = false
}

// The title field takes the focus as the dialog opens.
function focusTitle(event: Event): void {
  event.preventDefault()
  focusField()
}

function cancel(): void {
  discard()
  close()
}

/** Caused by is a bug's property: what was typed for one is not sent once the type is another. */
const sent = () => ({
  ...ticket,
  title: values.title,
  caused_by: ticket.type === 'bug' ? ticket.caused_by : '',
})

/** A refusal stays in the form with every typed value; the dialog closes once the board took it. */
const create = handleSubmit(async () => {
  const repository = ticket.repository
  if (!repositories.value.includes(repository)) return
  await send('POST', '/api/tickets', sent(), async (answer) => {
    saveText(LAST_REPOSITORY, repository)
    const id = answer.id
    if (id) {
      const open = { label: `Open ${id}`, run: () => void router?.push(ticketHref(repository, id)) }
      announce({ notice: `Created ${id}`, undo: null }, open)
    }
    await live?.refresh()
    close()
    discard()
    // The new card is brought into view, as it lands at the bottom of its column.
    await nextTick()
    if (id) document.querySelector(`[data-ticket="${id}"]`)?.scrollIntoView({ block: 'nearest' })
  })
}, focusField)

defineExpose({ open: show })
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent
      as="form"
      class="max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] gap-0 overflow-hidden p-0 sm:max-w-2xl"
      aria-label="New ticket"
      novalidate
      @submit="create($event)"
      @open-auto-focus="focusTitle($event)"
    >
      <DialogHeader class="border-b p-4 pr-12 sm:px-6 sm:pr-12">
        <DialogTitle>New ticket</DialogTitle>
        <DialogDescription>What it is and why; an agent picks it up from Spec.</DialogDescription>
      </DialogHeader>
      <FieldGroup class="min-h-0 gap-4 overflow-y-auto p-4 sm:px-6">
        <VeeField v-slot="{ value, handleChange, errors }" name="title">
          <Field :data-invalid="errors.length ? true : undefined">
            <FieldLabel :for="`${prefix}-title`">Title</FieldLabel>
            <Input
              :id="`${prefix}-title`"
              ref="title"
              name="title"
              :model-value="value"
              aria-required="true"
              :aria-invalid="errors.length ? true : undefined"
              :aria-describedby="errors.length ? `${prefix}-title-error` : undefined"
              placeholder="Ticket title"
              @update:model-value="handleChange($event)"
            />
            <FieldError v-if="errors.length" :id="`${prefix}-title-error`" :errors="errors" />
          </Field>
        </VeeField>
        <Field>
          <FieldLabel :for="`${prefix}-description`">Description</FieldLabel>
          <Textarea
            :id="`${prefix}-description`"
            :model-value="ticket.description"
            name="description"
            class="min-h-36"
            placeholder="What and why. Markdown; lines starting with - [ ] count as a checklist."
            @update:model-value="ticket.description = String($event)"
          />
        </Field>
        <section aria-label="Properties">
          <PropertyGroups
            :model-value="ticket"
            :prefix="prefix"
            mode="create"
            :repositories="repositories"
            folded
          />
        </section>
        <FieldError v-if="error">{{ error }}</FieldError>
      </FieldGroup>
      <DialogFooter class="flex-row justify-end border-t p-4 sm:px-6">
        <Button type="button" variant="outline" @click="cancel()">Cancel</Button>
        <Button type="submit" :disabled="busy || !repositories.includes(ticket.repository)"
          ><Spinner v-if="busy" data-icon="inline-start" />Create ticket</Button
        >
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
