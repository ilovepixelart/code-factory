<script setup lang="ts">
import SectionCard from '../components/SectionCard.vue'
import { ItemGroup } from '@/components/ui/item'
import { Tick02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed, nextTick, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import ReadState from '../components/ReadState.vue'
import InboxRow from '../components/inbox/InboxRow.vue'
import PullSize from '../components/PullSize.vue'
import {
  actionKeys,
  anchorOf,
  INBOX,
  itemHref as page,
  pagePrefix,
  rowId,
  ticketApi,
  useKeyedActions,
  useSectionPage,
} from '../components/inbox/inbox'
import InboxDiagnoses from '../components/inbox/InboxDiagnoses.vue'
import InboxIdle from '../components/inbox/InboxIdle.vue'
import InboxMain from '../components/inbox/InboxMain.vue'
import InboxMemory from '../components/inbox/InboxMemory.vue'
import InboxNav from '../components/inbox/InboxNav.vue'
import InboxPermissions from '../components/inbox/InboxPermissions.vue'
import InboxQuestions from '../components/inbox/InboxQuestions.vue'
import InboxReviews from '../components/inbox/InboxReviews.vue'
import InboxRules from '../components/inbox/InboxRules.vue'
import InboxScreens from '../components/inbox/InboxScreens.vue'
import InboxSessions from '../components/inbox/InboxSessions.vue'
import InboxStopped from '../components/inbox/InboxStopped.vue'
import { ask } from '../lib/actions'
import { notifying, setNotifying } from '../lib/attention'
import { clock } from '../lib/format'
import { SECTIONS, type Inbox, type InboxItem, type Section } from '../lib/metrics'
import { refusalText } from '../lib/notice'
import { fromAddress, LIST_SIZE, linkTo } from '../lib/paging'
import { usePolledRead } from '../lib/queries'
import { keys, POLL } from '../lib/queryKeys'
import { useQueryClient } from '@tanstack/vue-query'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Field, FieldLabel } from '@/components/ui/field'
import { Switch } from '@/components/ui/switch'
import { useEventListener } from '@vueuse/core'
import { inboxKeys } from '../components/inbox/keys'

// Everything that waits on the owner: each
// item leads with what it needs, then a quiet line saying whose it is; the item that has waited
// longest carries the page's one primary button. Typed answers survive each refresh.

const now = ref(Date.now() / 1000)
const route = useRoute()
const router = useRouter()
const notifyOn = ref('Notification' in window && notifying())
// A browser that refuses notifications leaves the switch out: it could not turn them on.
const blocked = ref('Notification' in window && Notification.permission === 'denied')

// A push notification links to its item as `/inbox#<id>` (CF-627): the first read that lists
// items opens the page of its section that holds it (CF-1196), then scrolls the page's own scroll
// area to it; later refreshes leave the scroll to the owner. `scrollIntoView` would also scroll
// the app's overflow-hidden panel and hide the top bar.
let aimed = false

async function openPageOf(id: string): Promise<void> {
  for (const section of SECTIONS) {
    const at = (inbox.value?.[section] ?? []).findIndex((item) => anchorOf(section, item) === id)
    if (at < 0) continue
    const prefix = pagePrefix(section)
    const { page: shown, size } = fromAddress(route.query, prefix, LIST_SIZE)
    const page = Math.floor(at / size) + 1
    if (page !== shown)
      await router.replace({
        query: linkTo(route.query, prefix, page, size, LIST_SIZE),
        hash: route.hash,
      })
    return
  }
}

function aimAt(id: string): void {
  const item = id ? document.getElementById(id) : null
  const area = item?.closest('[data-scroller]')
  if (item && area)
    area.scrollTop += item.getBoundingClientRect().top - area.getBoundingClientRect().top
}

const client = useQueryClient()
const read = usePolledRead(keys.inbox, (signal) => ask<Inbox>('/api/inbox', signal), POLL.inbox)
const inbox = read.data
const refresh = read.refresh
// Once the board has answered, the page stands until the next tick reads it.
const failed = computed(() =>
  inbox.value === null && read.query.error.value ? refusalText(read.query.error.value) : '',
)
watch(
  read.query.dataUpdatedAt,
  async () => {
    if (!inbox.value) return
    now.value = Date.now() / 1000
    if (aimed) return
    aimed = true
    await openPageOf(route.hash.slice(1))
    await nextTick()
    aimAt(route.hash.slice(1))
  },
  { immediate: true },
)

/** After a change: the items and the sidebar's count, both under `['inbox']`. */
async function changed(): Promise<void> {
  await client.invalidateQueries({ queryKey: keys.inbox.slice(0, 1) })
}

async function toggleNotify(): Promise<void> {
  await setNotifying(notifyOn.value)
  notifyOn.value = notifying()
  blocked.value = 'Notification' in window && Notification.permission === 'denied'
}

const push = computed(() => inbox.value?.push ?? null)
const nextUp = computed(() => inbox.value?.next_up ?? null)
const primary = (section: Section, index: number): 'default' | 'secondary' =>
  nextUp.value?.section === section && nextUp.value.index === index ? 'default' : 'secondary'

// What a refusal in the page's notice calls each section's item; a rule belongs to no ticket.
const id = (item: InboxItem): string => item.ticket?.id ?? ''
const names = {
  questions: (item: InboxItem) => `${id(item)} question`,
  permissions: (item: InboxItem) => `${id(item)} permission`,
  rules: (item: InboxItem) => `Rule ${item.reason}`,
  memory: (item: InboxItem) => `Memory proposal ${item.memory?.statement ?? ''}`,
  stopped: (item: InboxItem) => `${id(item)} stopped agent`,
  screens: (item: InboxItem) => `${id(item)} screens`,
  mergeable: (item: InboxItem) => `${id(item)} pull request`,
} satisfies Record<keyof typeof actionKeys, (item: InboxItem) => string>
/** The name of the listed item an action's key belongs to, '' when none is listed. */
const named = (key: string): string => {
  const sections = Object.entries(actionKeys) as [
    keyof typeof actionKeys,
    (item: InboxItem) => string,
  ][]
  for (const [section, keyOf] of sections) {
    const item = (inbox.value?.[section] ?? []).find((listed) => keyOf(listed) === key)
    if (item) return names[section](item)
  }
  return ''
}
const listed = (key: string): boolean => named(key) !== ''
const { busy, errors, run } = useKeyedActions(changed, listed, named)
provide(INBOX, { now, busy, errors, run, primary })
const empty = computed(() => SECTIONS.every((section) => !inbox.value?.[section]?.length))
// What the owner can act on in the Inbox, apart from sessions it can only open (CF-1196); the two
// groups are titled only where both are drawn.
const info: Section[] = ['sessions', 'diagnoses']
const acts = computed(() =>
  SECTIONS.some((section) => !info.includes(section) && inbox.value?.[section]?.length),
)
const informs = computed(() => info.some((section) => inbox.value?.[section]?.length))
const titled = computed(() => acts.value && informs.value)

// Captured on the window, so a key the Inbox uses (`n` on a permission) is not also the app's.
useEventListener(
  window,
  'keydown',
  inboxKeys(() => document.getElementById('inbox-region'), router),
  { capture: true },
)

const mergeable = useSectionPage('mergeable', () => inbox.value?.mergeable ?? null)
const failing = useSectionPage('failing', () => inbox.value?.failing ?? null)
</script>

<template>
  <Teleport to="#header-controls">
    <span v-if="push?.host" class="text-muted-foreground text-sm">Push to {{ push.host }}</span>
    <Field v-if="!blocked" orientation="horizontal" class="w-auto">
      <Switch id="notify-toggle" v-model="notifyOn" @update:model-value="toggleNotify()" />
      <FieldLabel for="notify-toggle">Desktop notifications</FieldLabel>
    </Field>
  </Teleport>
  <div v-if="inbox" id="inbox-region" class="page-wide grid grid-cols-1 gap-6">
    <Alert v-if="push?.failure" role="region" aria-labelledby="push-failure-heading">
      <AlertTitle id="push-failure-heading">Push notifications fail</AlertTitle>
      <AlertDescription>
        Sending{{ push.host ? ` to ${push.host}` : '' }} failed at {{ clock(push.failure.at) }}:
        {{ push.failure.problem }}. What waits is sent again on the next try.
      </AlertDescription>
    </Alert>

    <SectionCard v-if="empty" heading="inbox-empty" title="Needs you" empty>
      <template #empty>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"
              ><HugeiconsIcon :icon="Tick02Icon" aria-hidden="true"
            /></EmptyMedia>
            <EmptyTitle>Nothing needs you</EmptyTitle>
            <EmptyDescription
              >Agents ask here when they need you: questions, permissions, reviews and
              merges.</EmptyDescription
            >
          </EmptyHeader>
        </Empty>
      </template>
    </SectionCard>

    <div
      v-if="acts"
      :role="titled ? 'group' : undefined"
      :aria-labelledby="titled ? 'inbox-act' : undefined"
      class="grid grid-cols-1 gap-3"
    >
      <h2
        v-if="titled"
        id="inbox-act"
        class="text-xs font-medium tracking-wider text-muted-foreground uppercase"
      >
        Act now
      </h2>
      <div class="grid grid-cols-1 gap-6">
        <InboxMain :items="inbox.main" />

        <InboxQuestions :items="inbox.questions" />

        <InboxPermissions :items="inbox.permissions" />

        <InboxRules :items="inbox.rules" />

        <InboxMemory :items="inbox.memory" />

        <InboxStopped :items="inbox.stopped" />

        <InboxScreens :items="inbox.screens" />

        <SectionCard
          v-if="inbox.mergeable.length"
          key="mergeable"
          heading="inbox-mergeable"
          title="Ready to merge"
          :count="inbox.mergeable.length"
          description="CI passed; the merge waits for you"
        >
          <ItemGroup class="gap-3">
            <template v-for="(item, n) in mergeable.paged.rows.value" :key="page(item)">
              <InboxRow
                :id="rowId('mergeable', item)"
                :item="item"
                :now="now"
                :error="errors[actionKeys.mergeable(item)] ?? ''"
              >
                <template #actions>
                  <PullSize :pull="item.size" />
                  <Button as-child variant="ghost"
                    ><a :href="item.reason">Open pull request</a></Button
                  >
                  <Button
                    type="button"
                    :variant="primary('mergeable', mergeable.offset.value + n)"
                    :disabled="busy.has(actionKeys.mergeable(item))"
                    @click="run(actionKeys.mergeable(item), 'POST', `${ticketApi(item)}/merge`)"
                  >
                    <Spinner
                      v-if="busy.has(actionKeys.mergeable(item))"
                      data-icon="inline-start"
                    />Merge
                  </Button>
                </template>
                <p v-if="item.note" class="text-muted-foreground break-words text-sm">
                  {{ item.note }}
                </p>
              </InboxRow>
            </template>
          </ItemGroup>
          <InboxNav section="mergeable" label="pull requests to merge" :paged="mergeable.paged" />
        </SectionCard>

        <SectionCard
          v-if="inbox.failing.length"
          key="failing"
          heading="inbox-failing"
          title="Failing checks"
          :count="inbox.failing.length"
          description="CI failed on an open pull request, or its fix rounds ran out"
        >
          <ItemGroup class="gap-3">
            <template v-for="(item, n) in failing.paged.rows.value" :key="page(item)">
              <InboxRow :id="rowId('failing', item)" :item="item" :now="now">
                <template #actions>
                  <Button as-child :variant="primary('failing', failing.offset.value + n)"
                    ><a :href="item.reason">Open pull request</a></Button
                  >
                </template>
                <p v-if="item.note" class="text-muted-foreground break-words text-sm">
                  {{ item.note }}
                </p>
              </InboxRow>
            </template>
          </ItemGroup>
          <InboxNav section="failing" label="failing pull requests" :paged="failing.paged" />
        </SectionCard>

        <InboxIdle :items="inbox.idle ?? []" />

        <InboxReviews :items="inbox.reviews" />
      </div>
    </div>

    <div
      v-if="informs"
      :role="titled ? 'group' : undefined"
      :aria-labelledby="titled ? 'inbox-info' : undefined"
      class="grid grid-cols-1 gap-3"
    >
      <h2
        v-if="titled"
        id="inbox-info"
        class="text-xs font-medium tracking-wider text-muted-foreground uppercase"
      >
        For your information
      </h2>
      <InboxSessions :items="inbox.sessions" />
      <InboxDiagnoses :items="inbox.diagnoses" />
    </div>
  </div>
  <ReadState v-else shape="list" what="the inbox" :failed="failed" @retry="void refresh()" />
</template>
