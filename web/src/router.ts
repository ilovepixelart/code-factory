import {
  Activity01Icon,
  Analytics01Icon,
  Archive02Icon,
  BotIcon,
  CheckListIcon,
  InboxIcon,
  KanbanIcon,
  UserGroupIcon,
} from '@hugeicons/core-free-icons'
import { createRouter, createWebHistory } from 'vue-router'
import { shownTab } from './lib/analytics'
import { freshLoad, UPDATED } from './lib/build'
import { failed } from './lib/notice'
import type { RouteLocationNormalized } from 'vue-router'

/** A hidden Analytics tab's address leads to Flow, keeping its query and hash. */
const toFlowWhileHidden = (to: RouteLocationNormalized) =>
  shownTab(to.path) ? true : { path: '/analytics', query: to.query, hash: to.hash }
// Each page is its own chunk, read the first time it is shown (router.vuejs.org lazy loading).
const AgentsPage = () => import('./pages/AgentsPage.vue')
const ArchivePage = () => import('./pages/ArchivePage.vue')
const DesignPage = () => import('./pages/DesignPage.vue')
const FactoryBenchmarksPage = () => import('./pages/FactoryBenchmarksPage.vue')
const FactoryImprovementPage = () => import('./pages/FactoryImprovementPage.vue')
const FactoryPage = () => import('./pages/FactoryPage.vue')
const FactoryScorersPage = () => import('./pages/FactoryScorersPage.vue')
const FlowPage = () => import('./pages/FlowPage.vue')
const InboxPage = () => import('./pages/InboxPage.vue')
const MemoryPage = () => import('./pages/MemoryPage.vue')
const NotFound = () => import('./pages/NotFound.vue')
const ReplyPage = () => import('./pages/ReplyPage.vue')
const SessionPage = () => import('./pages/SessionPage.vue')
const SessionsPage = () => import('./pages/SessionsPage.vue')
const TeamPage = () => import('./pages/TeamPage.vue')
const TicketPage = () => import('./pages/TicketPage.vue')
const TicketsPage = () => import('./pages/TicketsPage.vue')

export const PAGES = [
  { path: '/', name: 'Sessions', icon: Activity01Icon },
  { path: '/tickets', name: 'Tickets', icon: KanbanIcon },
  { path: '/inbox', name: 'Inbox', icon: InboxIcon },
  { path: '/analytics', name: 'Analytics', icon: Analytics01Icon },
  { path: '/archive', name: 'Archive', icon: Archive02Icon },
  { path: '/memory', name: 'Memory', icon: CheckListIcon },
  { path: '/agents', name: 'Agents', icon: BotIcon },
  { path: '/team', name: 'Team', icon: UserGroupIcon },
] as const

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/tickets', component: TicketsPage, meta: { title: 'Tickets', list: false } },
    { path: '/tickets/list', component: TicketsPage, meta: { title: 'Tickets', list: true } },
    {
      path: '/tickets/:repository/:id',
      component: TicketPage,
      meta: { title: '' },
    },
    { path: '/', component: SessionsPage, meta: { title: 'Sessions' } },
    { path: '/sessions/:id', component: SessionPage, meta: { title: '' } },
    { path: '/inbox', component: InboxPage, meta: { title: 'Inbox' } },
    { path: '/analytics', component: FlowPage, meta: { title: 'Flow' } },
    { path: '/analytics/factory', component: FactoryPage, meta: { title: 'Factory' } },
    { path: '/analytics/scorers', component: FactoryScorersPage, meta: { title: 'Scorers' } },
    // Hidden until the evals that feed them exist (HIDDEN_TABS): their addresses lead to Flow.
    {
      path: '/analytics/benchmarks',
      component: FactoryBenchmarksPage,
      meta: { title: 'Benchmarks' },
      beforeEnter: toFlowWhileHidden,
    },
    {
      path: '/analytics/self-improvement',
      component: FactoryImprovementPage,
      meta: { title: 'Self-improvement' },
      beforeEnter: toFlowWhileHidden,
    },
    // The addresses the pages had before they joined Analytics, kept for links and bookmarks.
    { path: '/flow', redirect: (to) => ({ path: '/analytics', query: to.query, hash: to.hash }) },
    {
      path: '/factory/:page(scorers|benchmarks|self-improvement)?',
      redirect: (to) => ({
        path: `/analytics/${typeof to.params.page === 'string' && to.params.page !== '' ? to.params.page : 'factory'}`,
        query: to.query,
        hash: to.hash,
      }),
    },
    { path: '/archive', component: ArchivePage, meta: { title: 'Archive' } },
    { path: '/memory', component: MemoryPage, meta: { title: 'Memory' } },
    { path: '/agents', component: AgentsPage, meta: { title: 'Agents' } },
    { path: '/team', component: TeamPage, meta: { title: 'Team' } },
    { path: '/design', component: DesignPage, meta: { title: 'Design' } },
    { path: '/reply/:token([0-9a-f]{64})', component: ReplyPage, meta: { title: 'Reply' } },
    { path: '/:rest(.*)*', component: NotFound, meta: { title: 'Not found' } },
  ],
})

// A tab opened before an upgrade asks for page chunks the new build no longer has: load the
// address afresh, once, so the new build serves it (vite.dev/guide/build#load-error-handling).
// When that load did not bring it either, the notice says so rather than leave the page blank.
export function reloadForStaleChunk(error: unknown, to: { fullPath: string }): void {
  if (!/dynamically imported module|Importing a module script failed/.test(String(error))) return
  if (sessionStorage.getItem('codeFactoryReloaded') === to.fullPath) {
    failed(UPDATED)
    return
  }
  sessionStorage.setItem('codeFactoryReloaded', to.fullPath)
  window.location.assign(to.fullPath)
}
router.onError(reloadForStaleChunk)

// A tab whose build the board has left (CF-1298) loads the next address afresh, never reloads by itself.
router.beforeEach((to) => {
  const fresh = freshLoad(to.fullPath)
  if (fresh === null) return true
  window.location.assign(fresh)
  return false
})
