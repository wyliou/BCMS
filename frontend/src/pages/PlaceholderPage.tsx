import { Center, Text } from '@mantine/core';

/**
 * Props for the PlaceholderPage component.
 */
interface PlaceholderPageProps {
  /** The name to display in the placeholder. */
  name: string;
}

/**
 * PlaceholderPage is a temporary stub page for routes that have not
 * yet been implemented. Will be replaced in later batches.
 *
 * @param props - The component props.
 * @returns A centered placeholder message.
 */
export function PlaceholderPage({ name }: PlaceholderPageProps) {
  return (
    <Center py="xl">
      <Text c="dimmed">{name}</Text>
    </Center>
  );
}
