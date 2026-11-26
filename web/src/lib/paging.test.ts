import { expect, test } from 'vitest'
import { fromAddress, lastPage, linkTo, numbers, rangeText, slicePage } from './paging'

// CF-1191-R5: an address that names nothing usable reads as page 1 at the list's size.
test('page_from_the_address_falls_back_to_defaults', () => {
  expect(fromAddress({}, '', 50)).toEqual({ page: 1, size: 50 })
  expect(fromAddress({ page: '3', size: '10' }, '', 50)).toEqual({ page: 3, size: 10 })
  expect(fromAddress({ page: 'abc', size: '7' }, '', 50)).toEqual({ page: 1, size: 50 })
  expect(fromAddress({ page: '0', size: '0' }, '', 50)).toEqual({ page: 1, size: 50 })
  expect(fromAddress({ page: '-2', size: '2.5' }, '', 50)).toEqual({ page: 1, size: 50 })
  expect(fromAddress({ page: '2.0', size: '101' }, '', 50)).toEqual({ page: 1, size: 50 })
  expect(fromAddress({ page: '02', size: '010' }, '', 50)).toEqual({ page: 1, size: 50 })
  expect(fromAddress({ page: ['2', '4'], size: '100' }, '', 50)).toEqual({ page: 2, size: 100 })
  // A prefixed list reads its own keys and leaves the others alone.
  expect(fromAddress({ page: '9', factory_page: '2' }, 'factory_', 10)).toEqual({
    page: 2,
    size: 10,
  })
})

// CF-1191-R5: the last page of 247 rows at 10 is 25; of none, page 1.
test('the_last_page_holds_the_last_rows', () => {
  expect(lastPage(247, 10)).toBe(25)
  expect(lastPage(250, 10)).toBe(25)
  expect(lastPage(251, 10)).toBe(26)
  expect(lastPage(0, 50)).toBe(1)
  expect(lastPage(1, 50)).toBe(1)
})

// CF-1191-R1: the first, the last, the current page and its neighbours, a gap for each skip.
test('page_numbers_show_the_ends_and_the_neighbours', () => {
  expect(numbers(2, 25)).toEqual([1, 2, 3, '…', 25])
  expect(numbers(3, 79)).toEqual([1, 2, 3, 4, '…', 79])
  expect(numbers(25, 25)).toEqual([1, '…', 24, 25])
  expect(numbers(10, 20)).toEqual([1, '…', 9, 10, 11, '…', 20])
  expect(numbers(1, 3)).toEqual([1, 2, 3])
  expect(numbers(1, 1)).toEqual([1])
})

// CF-1191-R1: the range in words.
test('the_range_says_which_rows_of_how_many', () => {
  expect(rangeText(2, 10, 247)).toBe('11 to 20 of 247')
  expect(rangeText(25, 10, 247)).toBe('241 to 247 of 247')
  expect(rangeText(1, 50, 790)).toBe('1 to 50 of 790')
  expect(rangeText(1, 50, 1)).toBe('1 to 1 of 1')
})

// CF-1191-R3: a link keeps every other key and leaves out page 1 and the default size.
test('a_page_link_keeps_the_address_and_leaves_out_defaults', () => {
  const query = { q: 'gate', sort: 'id', page: '4', size: '10' }
  expect(linkTo(query, '', 2, 10, 50)).toEqual({ q: 'gate', sort: 'id', page: '2', size: '10' })
  expect(linkTo(query, '', 1, 10, 50)).toEqual({ q: 'gate', sort: 'id', size: '10' })
  expect(linkTo(query, '', 1, 50, 50)).toEqual({ q: 'gate', sort: 'id' })
  expect(linkTo({ page: '3' }, 'factory_', 2, 10, 10)).toEqual({ page: '3', factory_page: '2' })
})

// CF-1191-R7: a page is the slice of the rows it names; past the last, the last.
test('a_page_is_its_slice_of_the_rows', () => {
  const rows = Array.from({ length: 25 }, (_, n) => n + 1)
  expect(slicePage(rows, 1, 10)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
  expect(slicePage(rows, 3, 10)).toEqual([21, 22, 23, 24, 25])
  expect(slicePage(rows, 9, 10)).toEqual([21, 22, 23, 24, 25])
  expect(slicePage([], 4, 10)).toEqual([])
})
