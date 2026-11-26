<script setup lang="ts">
import { GROUPS, SHORTCUTS } from '../lib/shortcuts'
import { useOverlay } from '../lib/overlayHistory'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Kbd, KbdGroup } from '@/components/ui/kbd'

const open = useOverlay()
// Every shortcut under the group it works in, the groups in the registry's order.
const grouped = GROUPS.map((group) => ({
  group,
  shortcuts: SHORTCUTS.filter((s) => s.group === group),
})).filter((g) => g.shortcuts.length)
defineExpose({ open: () => (open.value = true) })
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent aria-describedby="">
      <DialogHeader>
        <DialogTitle>Keyboard shortcuts</DialogTitle>
      </DialogHeader>
      <div class="grid gap-5">
        <section
          v-for="{ group, shortcuts } in grouped"
          :key="group"
          :aria-labelledby="`shortcuts-${group}`"
        >
          <h3 :id="`shortcuts-${group}`" class="text-sm font-medium text-muted-foreground">
            {{ group }}
          </h3>
          <dl class="mt-2 grid grid-cols-[1fr_auto] gap-x-6 gap-y-2">
            <template v-for="shortcut in shortcuts" :key="shortcut.label">
              <dt>{{ shortcut.label }}</dt>
              <dd>
                <KbdGroup>
                  <Kbd v-for="key in shortcut.keys" :key="key">{{ key }}</Kbd>
                </KbdGroup>
              </dd>
            </template>
          </dl>
        </section>
      </div>
    </DialogContent>
  </Dialog>
</template>
