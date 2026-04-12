import { createTheme, MantineColorsTuple } from '@mantine/core';

/**
 * Generates a 10-shade color tuple from a primary hex color.
 * The primary shade is placed at index 6 per Mantine convention.
 *
 * @param hex - The primary hex color value.
 * @returns A 10-element tuple of color shades.
 */
function generateShades(hex: string): MantineColorsTuple {
  // Parse hex to RGB
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);

  const shades: string[] = [];
  // Reason: Generate 10 shades from lightest (index 0) to darkest (index 9)
  // with the original color at index 6
  for (let i = 0; i < 10; i++) {
    const mix = (c: number): number => {
      if (i < 6) {
        // Lighten: mix toward white (255)
        const lightFactor = 1 - i / 6;
        return Math.round(c + (255 - c) * lightFactor);
      }
      if (i === 6) return c;
      // Darken: mix toward black (0)
      const darkFactor = (i - 6) / 3;
      return Math.round(c * (1 - darkFactor * 0.4));
    };
    const sr = mix(r).toString(16).padStart(2, '0');
    const sg = mix(g).toString(16).padStart(2, '0');
    const sb = mix(b).toString(16).padStart(2, '0');
    shades.push(`#${sr}${sg}${sb}`);
  }

  return shades as unknown as MantineColorsTuple;
}

const brandPrimary: MantineColorsTuple = generateShades('#1B4F8A');
const brandSecondary: MantineColorsTuple = generateShades('#2D7DD2');
const statusNotUploaded: MantineColorsTuple = generateShades('#6B7280');
const statusUploaded: MantineColorsTuple = generateShades('#16A34A');
const statusResubmit: MantineColorsTuple = generateShades('#D97706');
const statusOverdue: MantineColorsTuple = generateShades('#DC2626');

/**
 * Mantine theme configured with PRD section 8.1 design tokens.
 * Custom colors are defined as full 10-shade tuples with the primary shade at index 6.
 */
export const theme = createTheme({
  primaryColor: 'brandPrimary',
  colors: {
    brandPrimary,
    brandSecondary,
    statusNotUploaded,
    statusUploaded,
    statusResubmit,
    statusOverdue,
  },
  other: {
    surfaceBase: '#F4F6F9',
  },
});
