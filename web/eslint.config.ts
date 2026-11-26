import pluginVue from 'eslint-plugin-vue'
import vueA11y from 'eslint-plugin-vuejs-accessibility'
import playwright from 'eslint-plugin-playwright'
import { withVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

export default withVueTs(
  { ignores: ['dist/**', 'src/generated/**'] },
  pluginVue.configs['flat/recommended'],
  vueA11y.configs['flat/recommended'],
  vueTsConfigs.strictTypeChecked,
  vueTsConfigs.stylisticTypeChecked,
  {
    rules: {
      'vue/no-v-html': 'error',
      'vue/component-api-style': ['error', ['script-setup']],
      'vue/block-lang': ['error', { script: { lang: 'ts' } }],
      'vue/define-macros-order': 'error',
      'vue/no-unused-refs': 'error',
      'vue/require-typed-ref': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      'vue/block-order': ['error', { order: ['script', 'template', 'style'] }],
      'vue/component-name-in-template-casing': 'error',
      'vue/custom-event-name-casing': 'error',
      'vue/define-emits-declaration': 'error',
      'vue/define-props-declaration': 'error',
      'vue/html-button-has-type': 'error',
      'vue/match-component-import-name': 'error',
      'vue/next-tick-style': 'error',
      'vue/no-boolean-default': 'error',
      'vue/no-duplicate-attr-inheritance': 'error',
      'vue/no-duplicate-class-names': 'error',
      'vue/no-empty-component-block': 'error',
      'vue/no-import-compiler-macros': 'error',
      'vue/no-multiple-objects-in-class': 'error',
      'vue/no-negated-v-if-condition': 'error',
      'vue/no-ref-object-reactivity-loss': 'error',
      'vue/no-setup-props-reactivity-loss': 'error',
      'vue/no-static-inline-styles': 'error',
      'vue/no-template-target-blank': 'error',
      'vue/no-undef-components': ['error', { ignorePatterns: ['RouterLink', 'RouterView'] }],
      'vue/no-undef-directives': 'error',
      'vue/no-undef-properties': 'error',
      'vue/no-unused-emit-declarations': 'error',
      'vue/no-unused-properties': 'error',
      'vue/no-use-v-else-with-v-for': 'error',
      'vue/no-useless-mustaches': 'error',
      'vue/no-useless-v-bind': 'error',
      'vue/no-v-text': 'error',
      'vue/prefer-define-options': 'error',
      'vue/prefer-prop-type-boolean-first': 'error',
      'vue/prefer-separate-static-class': 'error',
      'vue/prefer-true-attribute-shorthand': 'error',
      'vue/prefer-use-template-ref': 'error',
      'vue/require-explicit-slots': 'error',
      'vue/require-macro-variable-name': 'error',
      'vue/require-typed-object-prop': 'error',
      'vue/slot-name-casing': 'error',
      'vue/v-if-else-key': 'error',
      'vue/v-on-handler-style': ['error', 'inline'],
      'vue/eqeqeq': 'error',
      // Records keyed by stage or question are reactive objects on purpose; a Map would not be.
      '@typescript-eslint/no-dynamic-delete': 'off',
      // The backend cognitive complexity threshold (CF-458).
      complexity: ['error', 15],
    },
  },
  {
    // A function and a file a reader can hold (CF-458, CF-535); tests read as specifications and
    // are left out.
    files: ['src/**/*.ts', 'src/**/*.vue'],
    ignores: ['src/**/*.test.ts', 'src/test/**'],
    rules: {
      'max-lines-per-function': ['error', { max: 80, skipBlankLines: true, skipComments: true }],
      // A component or module a reader can take in at once (CF-535).
      'max-lines': ['error', { max: 300, skipBlankLines: true, skipComments: true }],
    },
  },
  {
    // A form copies its start once as Vue's docs advise for a prop used as an initial value:
    // the parent rebuilds it on every poll, and following it would wipe what the person types.
    files: [
      'src/components/MemoryForm.vue',
      'src/components/AgentForm.vue',
      'src/components/ConnectionForm.vue',
      'src/components/MemoryReview.vue',
    ],
    rules: { 'vue/no-setup-props-reactivity-loss': 'off' },
  },
  {
    // AI Elements' patterns, copied into src/components/ai/<Name>/ under the names their docs give.
    files: ['src/components/ai/**/*.vue'],
    rules: { 'vue/multi-word-component-names': 'off' },
  },
  {
    // shadcn-vue's components, written by its CLI (web/components.json) and kept as it writes them
    // so a later `add` or `diff` merges cleanly: only the house style rules they trip are off.
    files: ['src/components/ui/**/*.vue', 'src/components/ui/**/*.ts'],
    rules: {
      '@typescript-eslint/array-type': 'off',
      '@typescript-eslint/no-base-to-string': 'off',
      '@typescript-eslint/no-confusing-void-expression': 'off',
      '@typescript-eslint/no-empty-function': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-generated-empty-object-type': 'off',
      '@typescript-eslint/no-non-null-assertion': 'off',
      '@typescript-eslint/no-redundant-type-constituents': 'off',
      '@typescript-eslint/no-unnecessary-condition': 'off',
      '@typescript-eslint/no-unnecessary-type-assertion': 'off',
      '@typescript-eslint/no-unused-expressions': 'off',
      '@typescript-eslint/non-nullable-type-assertion-style': 'off',
      '@typescript-eslint/prefer-function-type': 'off',
      '@typescript-eslint/prefer-nullish-coalescing': 'off',
      '@typescript-eslint/prefer-optional-chain': 'off',
      '@typescript-eslint/restrict-template-expressions': 'off',
      'vue/define-macros-order': 'off',
      'vue/html-button-has-type': 'off',
      'vue/multi-word-component-names': 'off',
      'vue/no-boolean-default': 'off',
      'vue/no-duplicate-attr-inheritance': 'off',
      'vue/no-setup-props-reactivity-loss': 'off',
      'vue/no-static-inline-styles': 'off',
      'vue/no-undef-properties': 'off',
      'vue/no-unused-properties': 'off',
      'vue/no-useless-mustaches': 'off',
      'vue/prefer-use-template-ref': 'off',
      'vue/require-default-prop': 'off',
      'vue/require-explicit-slots': 'off',
      'vue/require-macro-variable-name': 'off',
      'vue/require-typed-ref': 'off',
      'vue/slot-name-casing': 'off',
      'vue/v-on-handler-style': 'off',
      'vuejs-accessibility/click-events-have-key-events': 'off',
      'vuejs-accessibility/form-control-has-label': 'off',
      'vuejs-accessibility/label-has-for': 'off',
      'vuejs-accessibility/no-static-element-interactions': 'off',
    },
  },
  {
    ...playwright.configs['flat/recommended'],
    files: ['e2e/**/*.ts'],
    rules: {
      ...playwright.configs['flat/recommended'].rules,
      'playwright/expect-expect': [
        'warn',
        {
          // vue_ticket_view runs each of these on the page and the panel; they hold the expects.
          assertFunctionNames: [
            'e2e_a_long_title_wraps_once',
            'e2e_the_ticket_page_scrolls_once',
            'e2e_a_long_code_value_ends_in_an_ellipsis',
            'e2e_the_stage_line_agrees_with_the_column',
            'e2e_the_stage_shows_once',
            'e2e_a_link_stays_inside_its_card',
            'e2e_the_footer_lines_up_with_the_columns',
          ],
        },
      ],
      'playwright/no-raw-locators': 'error',
      'playwright/no-nth-methods': 'error',
      'playwright/prefer-strict-equal': 'error',
      'playwright/no-magic-timeouts': 'error',
      'playwright/no-get-by-title': 'error',
      'playwright/prefer-native-locators': 'error',
    },
  },
  skipFormatting,
)
