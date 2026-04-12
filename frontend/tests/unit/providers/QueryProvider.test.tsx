import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useQueryClient } from '@tanstack/react-query';
import { QueryProvider } from '../../../src/providers/QueryProvider';

/**
 * Test child component that accesses the QueryClient.
 */
function TestChild() {
  const client = useQueryClient();
  return <div data-testid="child">{client ? 'has-client' : 'no-client'}</div>;
}

describe('QueryProvider', () => {
  it('renders children without error', () => {
    render(
      <QueryProvider>
        <div data-testid="child">Hello</div>
      </QueryProvider>,
    );
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('provides a QueryClient to children', () => {
    render(
      <QueryProvider>
        <TestChild />
      </QueryProvider>,
    );
    expect(screen.getByTestId('child').textContent).toBe('has-client');
  });

  it('provides the same QueryClient instance across re-renders', () => {
    const clients: ReturnType<typeof useQueryClient>[] = [];
    function Collector() {
      const client = useQueryClient();
      clients.push(client);
      return null;
    }

    const { rerender } = render(
      <QueryProvider>
        <Collector />
      </QueryProvider>,
    );
    rerender(
      <QueryProvider>
        <Collector />
      </QueryProvider>,
    );

    expect(clients[0]).toBe(clients[1]);
  });
});
