<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { LIST_SIZE, SIZES, lastPage, linkTo, numbers, rangeText } from '../lib/paging'
import { Button } from '@/components/ui/button'
import { ArrowLeft01Icon, ArrowRight01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination'

// The page control under a paged list (CF-1191): every page and size is a link, so a copied link
// and Back return to it; Previous on the first page and Next on the last are disabled buttons.
// Nothing shows while the list fits its first page.
const {
  total,
  page,
  size,
  label,
  prefix = '',
  fallback = LIST_SIZE,
} = defineProps<{
  total: number
  page: number
  size: number
  label: string
  prefix?: string
  fallback?: number
}>()

const route = useRoute()
const last = computed(() => lastPage(total, size))
const shown = computed(() => total > size || page > 1)
const pages = computed(() => numbers(page, last.value))
const to = (n: number, s = size) => ({
  path: route.path,
  query: linkTo(route.query, prefix, n, s, fallback),
})
</script>

<template>
  <Pagination
    v-if="shown"
    :aria-label="`Pages of ${label}`"
    :total="total"
    :items-per-page="size"
    :page="page"
    class="mt-3 flex-wrap items-center justify-start gap-x-3 gap-y-2"
  >
    <span
      data-testid="page-range"
      class="text-muted-foreground basis-full text-sm tabular-nums sm:basis-auto"
      >{{ rangeText(page, size, total) }}</span
    >
    <PaginationContent>
      <PaginationPrevious v-if="page > 1" key="previous-link" as-child>
        <RouterLink v-slot="{ href, navigate }" :to="to(page - 1)" custom
          ><a :href="href" rel="prev" @click="navigate($event)"
            ><HugeiconsIcon :icon="ArrowLeft01Icon" data-icon="inline-start" /><span
              class="hidden sm:block"
              >Previous</span
            ></a
          ></RouterLink
        >
      </PaginationPrevious>
      <PaginationPrevious v-else key="previous" />
      <template v-for="(n, i) in pages" :key="`${String(n)}-${String(i)}`">
        <PaginationEllipsis v-if="n === '…'" data-testid="page-number" class="hidden sm:flex" />
        <PaginationItem
          v-else
          :value="n"
          :is-active="n === page"
          as-child
          class="hidden tabular-nums sm:inline-flex"
        >
          <RouterLink v-slot="{ href, navigate }" :to="to(n)" custom
            ><a data-testid="page-number" :href="href" @click="navigate($event)">{{
              n
            }}</a></RouterLink
          >
        </PaginationItem>
      </template>
      <span data-testid="page-of" class="px-2 text-sm tabular-nums sm:hidden"
        >Page {{ page }} of {{ last }}</span
      >
      <PaginationNext v-if="page < last" key="next-link" as-child>
        <RouterLink v-slot="{ href, navigate }" :to="to(page + 1)" custom
          ><a :href="href" rel="next" @click="navigate($event)"
            ><span class="hidden sm:block">Next</span
            ><HugeiconsIcon :icon="ArrowRight01Icon" data-icon="inline-end"
          /></a>
        </RouterLink>
      </PaginationNext>
      <PaginationNext v-else key="next" />
    </PaginationContent>
    <DropdownMenu>
      <DropdownMenuTrigger as-child>
        <Button variant="ghost" class="ml-auto" data-testid="page-size">{{ size }} per page</Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="end" class="w-36" aria-label="Rows per page">
        <DropdownMenuGroup>
          <DropdownMenuItem v-for="s in SIZES" :key="s" as-child>
            <RouterLink v-slot="{ href, navigate }" :to="to(1, s)" custom
              ><a
                :href="href"
                :aria-current="s === size ? 'true' : undefined"
                @click="navigate($event)"
                >{{ s }} per page</a
              ></RouterLink
            >
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  </Pagination>
</template>
