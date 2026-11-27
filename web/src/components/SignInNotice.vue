<script setup lang="ts">
import { computed } from 'vue'
import AppMark from './AppMark.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { CodeBlockCopyButton } from '@/components/ui/code-block'

// What the shell shows in place of a page while the board refuses this browser's reads: the
// board's reason, capitalised, and how to sign in. The refusal carries no field that tells a
// sign-in refusal from another 403, so the instruction is always shown; a reason that ends in the
// same hint (`...: run uv run code-factory open`) keeps only what comes before it, so the card says
// it once. The shell keeps reading, so the page returns once signed in.
const { reason } = defineProps<{ reason: string }>()
const METHODS = [
  {
    name: 'Default browser',
    command: 'uv run code-factory open',
  },
  {
    name: 'This browser',
    command: 'uv run code-factory sign-in',
    detail: 'Open the link printed by the command within 60 seconds.',
  },
] as const
const HINT = /:\s*run uv run code-factory open\.?$/
const sentence = computed(() => {
  const why = HINT.test(reason) ? `${reason.replace(HINT, '')}.` : reason
  return why.charAt(0).toUpperCase() + why.slice(1)
})
</script>

<template>
  <div class="page-wide flex min-h-full flex-col items-center justify-center">
    <div class="flex w-full max-w-lg flex-col gap-4">
      <Card role="alert" aria-labelledby="sign-in-heading">
        <CardHeader>
          <span class="mb-2 flex items-center gap-2 font-medium"><AppMark />Code Factory</span>
          <CardTitle class="text-lg font-semibold"
            ><h2 id="sign-in-heading">This browser is not signed in</h2></CardTitle
          >
          <CardDescription>{{ sentence }}</CardDescription>
        </CardHeader>
        <CardContent class="grid gap-4">
          <p class="text-sm">Run one of these commands from your terminal.</p>
          <fieldset
            v-for="method in METHODS"
            :key="method.command"
            class="grid min-w-0 gap-2"
            :aria-label="method.name"
          >
            <p class="font-medium">{{ method.name }}</p>
            <div class="flex items-center gap-2 rounded-md bg-muted px-3 py-1.5">
              <code class="font-mono text-sm min-w-0 flex-1 wrap-anywhere">{{
                method.command
              }}</code>
              <CodeBlockCopyButton size="icon-sm" :value="method.command" />
            </div>
            <p v-if="'detail' in method" class="text-sm text-muted-foreground">
              {{ method.detail }}
            </p>
          </fieldset>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
