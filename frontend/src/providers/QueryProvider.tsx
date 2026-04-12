import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';

/**
 * Singleton QueryClient with application-wide default options.
 * Created outside the component body so it is not recreated on each render.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: true,
    },
    mutations: {
      retry: 0,
    },
  },
});

/**
 * QueryProvider wraps children in TanStack QueryClientProvider with
 * the shared singleton QueryClient.
 *
 * @param props.children - Child components that can use TanStack Query hooks.
 * @returns The provider-wrapped children.
 */
export function QueryProvider({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
