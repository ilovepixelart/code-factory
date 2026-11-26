<script setup lang="ts">
import { ArrowRight01Icon, File01Icon, Folder01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import type { FileNode } from './tree'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

// AI Elements' File Tree: a folder opens on its children, drawn by this same component; a file
// emits its path when chosen.
defineProps<{ node: FileNode }>()
const emit = defineEmits<{ select: [path: string] }>()
defineOptions({ name: 'FileTreeNode' })
</script>

<template>
  <Collapsible v-if="node.type === 'folder'" default-open>
    <CollapsibleTrigger as-child>
      <Button type="button" variant="ghost" size="sm" class="w-full justify-start">
        <HugeiconsIcon
          :icon="ArrowRight01Icon"
          class="transition-transform group-data-[state=open]/button:rotate-90"
          aria-hidden="true"
        />
        <HugeiconsIcon :icon="Folder01Icon" aria-hidden="true" />
        {{ node.name }}
      </Button>
    </CollapsibleTrigger>
    <CollapsibleContent>
      <div class="ml-4 flex flex-col">
        <FileTreeNode
          v-for="child in node.children"
          :key="child.path"
          :node="child"
          @select="emit('select', $event)"
        />
      </div>
    </CollapsibleContent>
  </Collapsible>
  <Button
    v-else
    type="button"
    variant="ghost"
    size="sm"
    class="w-full justify-start"
    @click="emit('select', node.path)"
  >
    <HugeiconsIcon :icon="File01Icon" aria-hidden="true" />
    {{ node.name }}
  </Button>
</template>
