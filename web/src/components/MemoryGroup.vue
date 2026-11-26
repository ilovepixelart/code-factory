<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { LIST_SIZE, linkTo, usePaged } from '../lib/paging'
import type { MemoryRecord } from '../lib/memory'
import MemoryEntry from './MemoryEntry.vue'
import PageNav from './PageNav.vue'
import SectionCard from './SectionCard.vue'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ItemGroup } from '@/components/ui/item'

// The entries that load in one place, paged in the browser (CF-1195; `<group>-page` and
// `<group>-size` in the address). Not loaded stays closed until it holds the entry the address
// names; an address naming an entry shows the page that holds it.
const props = defineProps<{
  group: string
  title: string
  hint: string
  rows: MemoryRecord[]
  others: MemoryRecord[]
  hashed: string
}>()
defineEmits<{ changed: [] }>()

const route = useRoute()
const router = useRouter()
const prefix = computed(() => `${props.group}-`)
// A group is keyed by its name, so the prefix never changes under an instance.
// eslint-disable-next-line vue/no-ref-object-reactivity-loss
const paged = usePaged(() => props.rows, prefix.value, LIST_SIZE)
const keyOf = (r: { repository: string; id: string }): string => `${r.repository}/${r.id}`
const holdsHashed = computed(() => props.rows.some((r) => r.id === props.hashed))
// Not loaded folds: it opens by its Show button, or by itself when the address names an entry in it.
const folds = computed(() => props.group === 'off')
const open = ref(false)
watch(
  holdsHashed,
  (holds) => {
    if (holds) open.value = true
  },
  { immediate: true },
)

watch(
  () => props.hashed,
  () => {
    const at = props.rows.findIndex((r) => r.id === props.hashed)
    const shown = at < 0 ? 0 : Math.floor(at / paged.size.value) + 1
    if (shown > 0 && shown !== paged.page.value)
      void router.replace({
        query: linkTo(route.query, prefix.value, shown, paged.size.value, LIST_SIZE),
        hash: route.hash,
      })
  },
  { immediate: true },
)
</script>

<template>
  <Collapsible v-model:open="open" as-child :unmount-on-hide="false" :disabled="!folds">
    <SectionCard
      :heading="`memory-${group}`"
      :title="title"
      :count="rows.length"
      :description="hint"
    >
      <template v-if="folds" #action>
        <CollapsibleTrigger as-child>
          <Button type="button" variant="ghost" size="sm">{{ open ? 'Hide' : 'Show' }}</Button>
        </CollapsibleTrigger>
      </template>
      <component :is="folds ? CollapsibleContent : 'div'" class="flex flex-col gap-3">
        <ItemGroup>
          <MemoryEntry
            v-for="record in paged.rows.value"
            :key="keyOf(record)"
            :record="record"
            :others="others"
            :opened="record.id === hashed"
            @changed="$emit('changed')"
          />
        </ItemGroup>
        <PageNav
          :label="`${title} entries`"
          :total="paged.total.value"
          :page="paged.page.value"
          :size="paged.size.value"
          :prefix="prefix"
        />
      </component>
    </SectionCard>
  </Collapsible>
</template>
