<script setup lang="ts">
import {
  KeyboardIcon,
  Moon02Icon,
  PlusSignIcon,
  Search01Icon,
  Sun03Icon,
  UnfoldMoreIcon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { useQuery } from '@tanstack/vue-query'
import { computed, inject } from 'vue'
import { useRoute } from 'vue-router'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'
import { ask } from '../lib/actions'
import { ATTENTION } from '../lib/attention'
import { keys } from '../lib/queryKeys'
import { SHELL } from '../lib/shell'
import { keysOf } from '../lib/shortcuts'
import { PAGES } from '../router'
import AppMark from './AppMark.vue'

// The shell's sidebar on the page's own background, the page an inset panel beside it: the mark
// and the repository switcher, New ticket and Search with their keys, the pages grouped by what
// they are for, then the shortcut sheet, the theme and the owner at its foot.
const { darkTheme } = defineProps<{ darkTheme: boolean }>()

const route = useRoute()
const shell = inject(SHELL)
const attention = inject(ATTENTION)

const GROUPS: { label: string; paths: string[] }[] = [
  { label: 'Work', paths: ['/tickets', '/inbox'] },
  { label: 'Agents', paths: ['/', '/agents', '/team'] },
  { label: 'Insights', paths: ['/analytics', '/archive', '/memory'] },
]
const groups = computed(() =>
  GROUPS.map((group) => ({
    label: group.label,
    pages: group.paths.flatMap((path) => PAGES.filter((page) => page.path === path)),
  })),
)

// A page is current on its own address and below it, by whole segments: `/sessions` alone has no
// page, so only a session below it marks Sessions.
const under = (prefix: string) => route.path === prefix || route.path.startsWith(`${prefix}/`)
const current = (path: string) =>
  path === '/' ? route.path === '/' || route.path.startsWith('/sessions/') : under(path)
const waiting = computed(() => attention?.count.value ?? 0)
const linkName = (page: { path: string; name: string }) =>
  page.path === '/inbox' && waiting.value
    ? `${page.name}, ${String(waiting.value)} waiting`
    : page.name

// The tracked repositories, each a filter of the board by the address's `repository`.
const repositories = useQuery({
  queryKey: keys.repositories,
  queryFn: ({ signal }) => ask<unknown>('/api/repositories', signal),
})
const tracked = computed(() =>
  Array.isArray(repositories.data.value)
    ? repositories.data.value.filter((name): name is string => typeof name === 'string')
    : [],
)
const chosen = computed(() =>
  typeof route.query.repository === 'string' ? route.query.repository : '',
)

const themeName = computed(() => (darkTheme ? 'Light theme' : 'Dark theme'))
</script>

<template>
  <Sidebar collapsible="icon" variant="inset">
    <aside aria-label="Sidebar" class="flex min-h-0 flex-1 flex-col">
      <SidebarHeader>
        <!-- sidebar-07's switcher: the mark, the board's name and the repository in view, one row. -->
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <SidebarMenuButton
                  size="lg"
                  data-repository-switcher
                  :tooltip="chosen || 'All repositories'"
                  aria-label="Choose a repository"
                >
                  <div class="flex aspect-square size-8 items-center justify-center">
                    <AppMark />
                  </div>
                  <div class="grid flex-1 text-left text-sm leading-tight">
                    <span class="truncate font-semibold">Code Factory</span>
                    <span class="truncate text-sidebar-foreground/70">{{
                      chosen || 'All repositories'
                    }}</span>
                  </div>
                  <HugeiconsIcon :icon="UnfoldMoreIcon" class="ml-auto" aria-hidden="true" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="start"
                class="w-(--reka-dropdown-menu-trigger-width) min-w-56"
              >
                <DropdownMenuGroup>
                  <DropdownMenuItem as-child>
                    <RouterLink to="/tickets">All repositories</RouterLink>
                  </DropdownMenuItem>
                </DropdownMenuGroup>
                <DropdownMenuSeparator v-if="tracked.length" />
                <DropdownMenuGroup v-if="tracked.length">
                  <DropdownMenuItem v-for="name in tracked" :key="name" as-child>
                    <RouterLink :to="{ path: '/tickets', query: { repository: name } }">{{
                      name
                    }}</RouterLink>
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
        <SidebarMenu data-quick-actions>
          <SidebarMenuItem>
            <SidebarMenuButton
              type="button"
              data-action="new-ticket"
              :tooltip="`New ticket (${keysOf('new').join(' ')})`"
              :aria-keyshortcuts="keysOf('new').join(' ')"
              @click="shell?.newTicket()"
            >
              <HugeiconsIcon :icon="PlusSignIcon" aria-hidden="true" />
              <span>New ticket</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              type="button"
              data-action="search"
              tooltip="Search (⌘ K)"
              aria-keyshortcuts="Meta+K"
              @click="shell?.search()"
            >
              <HugeiconsIcon :icon="Search01Icon" aria-hidden="true" />
              <span>Search</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <nav aria-label="Pages">
          <SidebarGroup v-for="group in groups" :key="group.label" :aria-label="group.label">
            <SidebarGroupLabel class="uppercase tracking-wider">{{
              group.label
            }}</SidebarGroupLabel>
            <SidebarMenu>
              <SidebarMenuItem v-for="page in group.pages" :key="page.path">
                <SidebarMenuButton as-child :is-active="current(page.path)" :tooltip="page.name">
                  <RouterLink
                    :to="page.path"
                    :aria-current="current(page.path) ? 'page' : undefined"
                    :aria-label="linkName(page)"
                  >
                    <HugeiconsIcon
                      :icon="page.icon"
                      class="text-sidebar-foreground/70"
                      aria-hidden="true"
                    />
                    <span>{{ page.name }}</span>
                  </RouterLink>
                </SidebarMenuButton>
                <template v-if="page.path === '/inbox'">
                  <template v-if="waiting">
                    <SidebarMenuBadge
                      id="inbox-count"
                      :data-attention="waiting"
                      :data-latest="attention?.latest.value"
                      >{{ waiting }}</SidebarMenuBadge
                    >
                    <!-- The folded sidebar hides the badge: a dot on the icon still says
                         something waits. -->
                    <span
                      data-testid="inbox-dot"
                      aria-hidden="true"
                      class="pointer-events-none absolute top-1 right-1 hidden size-2 rounded-full bg-sidebar-primary group-data-[collapsible=icon]:block"
                    ></span>
                  </template>
                  <span v-else id="inbox-count" data-attention="0" data-latest="" hidden></span>
                </template>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroup>
        </nav>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              type="button"
              data-action="shortcuts"
              tooltip="Shortcuts (?)"
              aria-keyshortcuts="?"
              @click="shell?.shortcuts()"
            >
              <HugeiconsIcon :icon="KeyboardIcon" aria-hidden="true" />
              <span>Shortcuts</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              type="button"
              data-action="theme"
              :aria-label="themeName"
              :title="themeName"
              @click="shell?.toggleTheme()"
            >
              <HugeiconsIcon :icon="darkTheme ? Sun03Icon : Moon02Icon" aria-hidden="true" />
              <span>{{ themeName }}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </aside>
  </Sidebar>
</template>
