# Spec: Mantine Theme with Design Tokens (simple)

Module: `frontend/src/styles/theme.ts` | Tests: `frontend/tests/unit/styles/theme.test.ts`

## Exports
- `theme` — `MantineTheme` object: configured Mantine theme with all PRD §8.1 design tokens and custom color extensions.

## Imports
- `@mantine/core`: `createTheme`, `MantineColorsTuple`

## Design Tokens (PRD §8.1 — all must be present)

| Token name | Hex | Mantine key | Usage |
|---|---|---|---|
| `brand-primary` | `#1B4F8A` | `theme.colors.brandPrimary` | Main visual, navbar background |
| `brand-secondary` | `#2D7DD2` | `theme.colors.brandSecondary` | Interactive elements, links |
| `surface-base` | `#F4F6F9` | `theme.other.surfaceBase` | Page background (`AppShell.main` bg) |
| `status-not-uploaded` | `#6B7280` | `theme.colors.statusNotUploaded` | StatusBadge: not uploaded (grey) |
| `status-uploaded` | `#16A34A` | `theme.colors.statusUploaded` | StatusBadge: uploaded (green) |
| `status-resubmit` | `#D97706` | `theme.colors.statusResubmit` | StatusBadge: resubmit requested (amber) |
| `status-overdue` | `#DC2626` | `theme.colors.statusOverdue` | StatusBadge: overdue (red) |

Token colors must be represented as full 10-shade `MantineColorsTuple` arrays (primary shade at index 6 matches the hex above). The `primaryColor` for the Mantine theme is `'brandPrimary'`.

## Side-Effects
None — pure configuration object, no side effects.

## Gotchas
- Mantine 7 requires a 10-element color tuple even if only one shade is used; fill remaining entries with accessible lighter/darker variants generated from the primary hex.
- Status color hex values must ONLY appear in this file. All other components reference them via theme object. Violating this breaks FCR-003.
- `theme.other` is the escape hatch for non-color tokens (e.g., `surfaceBase` for page background).
- Do not set `theme.fontFamily` without confirming the font is available in the intranet deployment environment.

## Tests
1. `theme.colors.brandPrimary[6]` equals `#1B4F8A`.
2. `theme.colors.statusUploaded[6]` equals `#16A34A`.
3. `theme.colors.statusNotUploaded[6]` equals `#6B7280`.
4. `theme.colors.statusResubmit[6]` equals `#D97706`.
5. `theme.colors.statusOverdue[6]` equals `#DC2626`.

## Constraints
FCR-003: This component references status colors via the theme object (e.g., `theme.colors.statusUploaded`). No hardcoded hex color strings for status indicators.
FCR-007: Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
