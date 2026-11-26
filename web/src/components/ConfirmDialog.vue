<script setup lang="ts">
import { watch } from 'vue'
import { answer, question } from '../lib/confirm'
import { useOverlay } from '../lib/overlayHistory'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

// The page's confirmation dialog: Cancel holds the focus as it opens, so Enter on a fresh dialog
// does not delete. However it closes (Cancel, Escape, Back), the answer is no; the watcher runs
// after Delete's own click has answered yes. A question asked from a menu item, gone once the
// menu closes, gives the keyboard back to the menu's button instead.
const open = useOverlay()
let returnTo: HTMLElement | null = null
watch(
  () => question.answer,
  (asking) => {
    if (asking && !open.value) returnTo = origin()
    open.value = asking !== null
  },
)

function origin(): HTMLElement | null {
  const active = document.activeElement instanceof HTMLElement ? document.activeElement : null
  const menu = active?.closest('[role="menu"]')
  const button = menu && document.getElementById(menu.getAttribute('aria-labelledby') ?? '')
  return button ?? active
}

function giveBack(event: Event): void {
  const target = returnTo
  returnTo = null
  if (!target?.isConnected) return
  event.preventDefault()
  target.focus()
}
watch(open, (now) => {
  if (!now) answer(false)
})
</script>

<template>
  <AlertDialog v-model:open="open">
    <AlertDialogContent @close-auto-focus="giveBack($event)">
      <AlertDialogHeader>
        <AlertDialogTitle>{{ question.title }}</AlertDialogTitle>
        <AlertDialogDescription>
          {{ question.verb }} {{ question.text }}? Undo in the notice that follows brings it back.
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel>Cancel</AlertDialogCancel>
        <AlertDialogAction variant="destructive" @click="answer(true)">{{
          question.verb
        }}</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
