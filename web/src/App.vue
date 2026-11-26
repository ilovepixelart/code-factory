<script setup lang="ts">
import 'vue-sonner/style.css'
import { useColorMode, useCssVar, useEventListener, useResizeObserver } from '@vueuse/core'
import { computed, nextTick, onMounted, provide, ref, useTemplateRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'
import CommandMenu from './components/CommandMenu.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import NewTicket from './components/NewTicket.vue'
import ShortcutSheet from './components/ShortcutSheet.vue'
import SidebarNavigationClose from './components/SidebarNavigationClose.vue'
import SignInNotice from './components/SignInNotice.vue'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { ATTENTION, useAttention } from './lib/attention'
import { dialogOpen, gPending, sequence, typing } from './lib/keys'
import { AFTER_G } from './lib/shortcuts'
import { BOARD, useBoard } from './lib/live'
import { useNoticeToasts } from './lib/noticeToasts'
import { NEW_TICKET } from './lib/openTicket'
import { hourMinute } from './lib/format'
import { useUnanswered } from './lib/queries'
import { SHELL } from './lib/shell'
import { saveText } from './lib/storage'
import { Toaster } from '@/components/ui/sonner'

const route = useRoute()
const router = useRouter()
const live = useBoard()
provide(BOARD, live)
const toastLift = useNoticeToasts(() => live.refresh())

// While the board refuses this browser's reads, the header names the sign-in card the page gives
// way to, not the page it cannot show.
const signedOut = computed(() => live.refused.value !== '')
const title = computed(() => {
  if (signedOut.value) return 'Sign in'
  return typeof route.meta.title === 'string' ? route.meta.title : ''
})
// A ticket or a session has no route title (its page heads the header itself): the tab names the
// ticket or session its address opens.
const tabName = computed(() => {
  const id = route.params.id
  return title.value || (typeof id === 'string' ? id : '')
})
const attention = useAttention(() => tabName.value)
provide(ATTENTION, attention)
// The header's status word and its dot, whose colour alone tells the states apart. A page's own
// read that the board did not answer reconnects too, though the board itself is not read for it.
const unanswered = useUnanswered()
const liveState = computed(() =>
  live.state.value === 'live' && unanswered.value.failing ? 'reconnecting' : live.state.value,
)
const lastRead = computed(() =>
  unanswered.value.since === null ? '' : hourMinute(unanswered.value.since / 1000),
)
const LIVE_DOT = {
  connecting: 'bg-muted-foreground/40',
  live: 'bg-primary',
  reconnecting: 'bg-muted-foreground',
} as const
const folded = ref(document.documentElement.dataset.sidebar === 'folded')
// The sidebar's open state, kept where theme-early.js reads it before paint; SidebarProvider's own
// toggles (its trigger and Cmd+B) arrive here through update:open.
function setFolded(next: boolean): void {
  folded.value = next
  if (next) document.documentElement.dataset.sidebar = 'folded'
  else delete document.documentElement.dataset.sidebar
  saveText('codeFactorySidebar', next ? 'folded' : 'open')
}
function toggleSidebar(): void {
  setFolded(!folded.value)
}

// The first page's title and controls are teleported into the header once its component has
// mounted: the header and the page area stay unpainted until then, so the page does not jump
// as they arrive. Only the first paint is held; later navigations keep the shell shown.
const settled = ref(false)
onMounted(() => {
  void router
    .isReady()
    .then(nextTick)
    .finally(() => (settled.value = true))
})

// The theme as shadcn-vue's dark mode docs set it: the `dark` class on <html>, kept under the key
// theme-early.js reads before paint. No transition-blocking <style> element: the security policy
// refuses inline style.
const mode = useColorMode({ storageKey: 'codeFactoryTheme', disableTransition: false })
const dark = computed(() => mode.value === 'dark')

function toggleTheme(): void {
  mode.value = dark.value ? 'light' : 'dark'
}

const commands = useTemplateRef<InstanceType<typeof CommandMenu>>('commands')
const newTicket = useTemplateRef<InstanceType<typeof NewTicket>>('newTicket')
provide(NEW_TICKET, () => void newTicket.value?.open())
const sheet = useTemplateRef<InstanceType<typeof ShortcutSheet>>('sheet')
provide(SHELL, {
  search: () => commands.value?.open(),
  newTicket: () => void newTicket.value?.open(),
  shortcuts: () => sheet.value?.open(),
  toggleTheme,
})

// The page's own keys, each pressed alone outside a field or a dialog.
const OWN_KEYS: Record<string, () => void> = {
  '?': () => sheet.value?.open(),
  '[': toggleSidebar,
  n: () => void newTicket.value?.open(),
}
// `g` then a page's key within a second goes to that page (the Go to group in lib/shortcuts.ts).
function onKey(event: KeyboardEvent): void {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    commands.value?.open()
    return
  }
  if (event.metaKey || event.ctrlKey || event.altKey || typing(event.target) || dialogOpen()) return
  const own = OWN_KEYS[event.key]
  const page = AFTER_G[event.key]
  if (page && gPending()) {
    // Taken here, so a ticket's own key of the same letter does not also act.
    event.preventDefault()
    sequence.gAt = 0
    void router.push(page)
  } else if (own) {
    event.preventDefault()
    own()
  } else if (event.key === 'g') {
    sequence.gAt = Date.now()
  }
}

// The gutter the main element reserves on each edge, 0 with overlay scrollbars: the page body gives it back
// from its side padding, so its margin is the same on all four sides.
const scroller = useTemplateRef<HTMLElement>('scroller')
const gutter = useCssVar('--gutter', scroller)
function measureGutter(): void {
  const main = scroller.value
  if (main) gutter.value = `${String((main.offsetWidth - main.clientWidth) / 2)}px`
}
useResizeObserver(scroller, measureGutter)
useEventListener(document, 'keydown', onKey)
onMounted(measureGutter)
</script>

<template>
  <!-- WCAG 2.4.1: the first Tab stop skips the sidebar's links. -->
  <Button
    as-child
    variant="secondary"
    class="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:top-2 focus-visible:left-2 focus-visible:z-50 focus-visible:px-3 focus-visible:py-2"
    ><a href="#content">Skip to content</a></Button
  >
  <!-- Folded, the icon column is 2.5rem: the rail is 56 px with its 32 px buttons 16 px from either
       edge. Set on the sidebar, under SidebarProvider's inline default of 3rem. -->
  <SidebarProvider
    :open="!folded"
    class="h-svh **:data-[slot=sidebar]:[--sidebar-width-icon:2.5rem]"
    @update:open="setFolded(!$event)"
  >
    <SidebarNavigationClose />
    <AppSidebar :dark-theme="dark" />
    <SidebarInset
      id="content"
      tabindex="-1"
      :class="
        cn(
          'min-h-0 min-w-0 overflow-hidden outline-none md:border md:border-border/70',
          settled ? '' : 'invisible',
        )
      "
    >
      <header
        class="flex min-h-14 shrink-0 flex-wrap items-center gap-2 border-b bg-card px-4 py-2 md:px-6"
      >
        <SidebarTrigger class="-ml-1" title="Toggle sidebar ([)" />
        <Separator
          orientation="vertical"
          class="mx-2 data-[orientation=vertical]:h-4 data-[orientation=vertical]:self-center"
        />
        <h1 v-if="title" class="cn-font-heading text-lg font-semibold">{{ title }}</h1>
        <div id="header-title" class="contents"></div>
        <!-- min-w-22 holds the width of the longest status word, so a wrapped header keeps its
             rows when connecting gives way to live. -->
        <p class="flex min-w-22 items-center gap-1.5 text-sm text-muted-foreground">
          <span
            v-if="!signedOut"
            data-testid="live-dot"
            :class="cn('size-2 rounded-full', LIVE_DOT[liveState])"
            :data-state="liveState"
          ></span>
          <span aria-live="polite">{{ signedOut ? 'signed out' : liveState }}</span>
        </p>
        <p
          v-if="lastRead && !signedOut"
          data-testid="last-read"
          class="order-last basis-full text-sm text-muted-foreground"
        >
          The board did not answer; this page shows its last read, from {{ lastRead }}.
        </p>
        <div
          id="header-controls"
          class="ml-auto flex max-w-full min-w-0 flex-wrap items-center justify-end gap-2"
        ></div>
      </header>
      <!-- relative: what is absolutely positioned inside scrolls here, not with the document
           (CF-836). -->
      <div
        ref="scroller"
        data-scroller
        class="relative min-h-0 flex-1 overflow-auto [scrollbar-gutter:stable_both-edges]"
      >
        <SignInNotice v-if="live.refused.value" :reason="live.refused.value" />
        <RouterView v-else />
      </div>
    </SidebarInset>
  </SidebarProvider>
  <CommandMenu ref="commands" />
  <NewTicket ref="newTicket" />
  <ShortcutSheet ref="sheet" />
  <Toaster position="bottom-center" :offset="toastLift === null ? '24px' : { bottom: toastLift }" />
  <ConfirmDialog />
</template>
