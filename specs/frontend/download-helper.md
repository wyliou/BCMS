# Spec: File Download Helper (moderate)

Module: `frontend/src/lib/download.ts` | Tests: `frontend/tests/unit/lib/download.test.ts`

## FRs
- **FR-010:** Filing-unit manager downloads their Excel template from `GET /cycles/{cycle_id}/templates/{org_unit_id}/download`. Backend returns binary XLSX with `Content-Disposition: attachment`.
- **FR-017:** Consolidated report export uses an async pattern: `POST /cycles/{cycle_id}/reports/exports` returns either `{ mode: "sync", file_url, expires_at }` or `{ mode: "async", job_id }`. Async variant polls `GET /exports/{job_id}` for status, then downloads `GET /exports/{job_id}/file`.
- **FR-023:** Audit log export streams CSV from `GET /audit-logs/export`.

## Exports
- `downloadBlob(url: string, filename: string): Promise<void>` — downloads a file from a URL using the axios client; creates an object URL and triggers browser download via a temporary `<a>` element. Handles both sync blob and pre-signed file URLs.
- `pollAndDownload(jobId: string, pollUrl: string, fileUrl: string): Promise<void>` — polls `pollUrl` every 2 seconds until status is `"succeeded"`, then calls `downloadBlob(fileUrl, ...)`. Rejects if status becomes `"failed"` or if maximum poll iterations (150 = 5 minutes) are exceeded.

## Imports
- `../api/client`: `apiClient`

## Function Contracts

### `downloadBlob(url: string, filename: string): Promise<void>`

```typescript
async function downloadBlob(url: string, filename: string): Promise<void> {
  const response = await apiClient.get(url, {
    responseType: 'blob',
  });
  const objectUrl = URL.createObjectURL(response.data as Blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(objectUrl);
}
```

The anchor click triggers the native browser download dialog. `URL.revokeObjectURL` must be called after the click to avoid memory leaks.

### `pollAndDownload(jobId: string, pollUrl: string, fileUrl: string): Promise<void>`

```typescript
async function pollAndDownload(
  jobId: string,
  pollUrl: string,
  fileUrl: string
): Promise<void> {
  const MAX_POLLS = 150;
  const POLL_INTERVAL_MS = 2000;

  for (let i = 0; i < MAX_POLLS; i++) {
    const response = await apiClient.get<{ status: string; error_message?: string }>(pollUrl);
    const { status, error_message } = response.data;
    if (status === 'succeeded') {
      await downloadBlob(fileUrl, deriveFilenameFromUrl(fileUrl));
      return;
    }
    if (status === 'failed') {
      throw new Error(error_message ?? 'Export job failed');
    }
    await sleep(POLL_INTERVAL_MS);
  }
  throw new Error('Export timed out after 5 minutes');
}
```

`deriveFilenameFromUrl(url: string): string` is a private helper that extracts the filename from the URL path (e.g., `/exports/abc/file` → `export.xlsx`). Fallback to `'download'` if parsing fails.

`sleep(ms: number): Promise<void>` is a private helper: `new Promise(resolve => setTimeout(resolve, ms))`.

## Side-Effects
- `downloadBlob`: Creates and removes a temporary `<a>` element from `document.body`. Creates and revokes an object URL.
- `pollAndDownload`: Calls `apiClient.get` in a loop. Uses `setTimeout` via the `sleep` helper.

## Gotchas
- `URL.createObjectURL` and `document.createElement('a')` are the ONLY permitted programmatic download mechanisms. FCR-008 prohibits `window.open()` and other patterns.
- The `<a>` element must be appended to `document.body` before `.click()` — some browsers require this for the download to trigger.
- `pollAndDownload` must not use `setInterval`. It uses sequential `await` calls with `setTimeout` delays (FCR-006 prohibits `setInterval`).
- The `fileUrl` for `pollAndDownload` comes from `GET /exports/{job_id}/file` — the caller constructs it from the `job_id` by convention: `` `/exports/${jobId}/file` ``.
- In tests, mock `URL.createObjectURL`, `URL.revokeObjectURL`, and `document.createElement` with `vi.spyOn` or `vi.stubGlobal`.

## Tests
1. **downloadBlob success:** Calls `apiClient.get` with `responseType: 'blob'`; creates an object URL; appends and clicks an anchor; revokes the object URL.
2. **downloadBlob filename:** The anchor's `download` attribute equals the provided `filename` argument.
3. **pollAndDownload succeeds on first poll:** When `GET pollUrl` returns `{ status: 'succeeded' }`, immediately calls `downloadBlob`.
4. **pollAndDownload polls until succeeded:** When the first 2 polls return `{ status: 'running' }` and the 3rd returns `{ status: 'succeeded' }`, `downloadBlob` is called after 3 polls.
5. **pollAndDownload rejects on failure:** When `GET pollUrl` returns `{ status: 'failed', error_message: 'Export error' }`, the promise rejects with that message.

## Consistency Constraints
FCR-001: This module uses the shared `apiClient` from `src/api/client.ts` for all HTTP requests. It does NOT create its own axios instance or use raw `fetch()`. The CSRF token is read from `document.cookie` and set as `X-CSRF-Token` by the request interceptor.
FCR-008: File downloads in this component use `downloadBlob()` or `pollAndDownload()` from `src/lib/download.ts`. No manual `window.open()`, `a.click()`, or direct blob handling.
