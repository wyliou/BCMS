# Spec: StatusBadge Component (simple)

Module: `frontend/src/components/StatusBadge.tsx` | Tests: `frontend/tests/unit/components/StatusBadge.test.tsx`

## Exports
- `StatusBadge` — React component: renders a Mantine `Badge` with the correct color and label for a given budget status string.

## Imports
- `@mantine/core`: `Badge`, `useMantineTheme`
- `react-i18next`: `useTranslation`

## Props Interface
```typescript
type UploadStatus = 'not_uploaded' | 'uploaded' | 'resubmit' | 'overdue';

interface StatusBadgeProps {
  status: UploadStatus;
}
```

## Status-to-Token Mapping
| `status` | Mantine theme color key | i18n label key |
|---|---|---|
| `not_uploaded` | `theme.colors.statusNotUploaded[6]` | `status.not_uploaded` |
| `uploaded` | `theme.colors.statusUploaded[6]` | `status.uploaded` |
| `resubmit` | `theme.colors.statusResubmit[6]` | `status.resubmit` |
| `overdue` | `theme.colors.statusOverdue[6]` | `status.overdue` |

The color is applied via the Mantine `Badge` `color` prop using a custom color from `useMantineTheme()`. No inline hex strings.

## Side-Effects
None — pure presentational component.

## Gotchas
- Never hardcode hex values in this component. Hex strings live exclusively in `styles/theme.ts` (FCR-003).
- The `status` prop is typed as a union; the component should not render anything for unknown status values. Add a type guard or exhaustive check.
- WCAG AA: ensure the badge background+text combination maintains at least 4.5:1 contrast ratio. White text on the green/amber/red backgrounds should be verified.

## Tests
1. Renders `Badge` with the `status.uploaded` i18n label when `status="uploaded"`.
2. Renders `Badge` with the `status.not_uploaded` i18n label when `status="not_uploaded"`.
3. Renders `Badge` with the `status.resubmit` i18n label when `status="resubmit"`.
4. Renders `Badge` with the `status.overdue` i18n label when `status="overdue"`.
5. No hardcoded hex color strings in the rendered DOM output.

## Constraints
FCR-003: This component references status colors via the theme object (e.g., `theme.colors.statusUploaded`). No hardcoded hex color strings for status indicators.
FCR-004: All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
FCR-007: Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
