import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeAll, afterAll } from 'vitest';
import { setupServer } from 'msw/node';

// Reason: Mantine requires window.matchMedia which jsdom does not provide
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Reason: Mantine ScrollArea uses ResizeObserver which jsdom does not provide
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

/**
 * MSW server instance with empty default handlers.
 * Import `server` in test files to add per-test handlers via `server.use(...)`.
 */
export const server = setupServer();

// Start server before all tests; fail loudly on unhandled requests
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});

// Reset handlers after each test to prevent bleed-over
afterEach(() => {
  server.resetHandlers();
  // Unmount React trees to prevent DOM leaks between tests
  cleanup();
});

afterAll(() => {
  server.close();
});
