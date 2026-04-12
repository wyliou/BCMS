import { apiClient } from '../api/client';

/**
 * Pauses execution for a specified duration.
 *
 * @param ms - Milliseconds to sleep.
 * @returns A promise that resolves after the delay.
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Downloads a file from a URL using the shared API client.
 * Creates a temporary anchor element to trigger the browser download dialog.
 *
 * @param url - The API endpoint URL for the file.
 * @param filename - The filename for the downloaded file.
 */
export async function downloadBlob(url: string, filename: string): Promise<void> {
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

/** Maximum number of poll iterations before timeout (5 minutes at 2s intervals). */
const MAX_POLLS = 150;
/** Interval between poll requests in milliseconds. */
const POLL_INTERVAL_MS = 2000;

/**
 * Polls an export job status endpoint until the job succeeds or fails,
 * then downloads the result file.
 *
 * @param pollUrl - The URL to poll for job status.
 * @param fileUrl - The URL to download the file from once the job succeeds.
 * @throws Error if the job fails or polling times out after 5 minutes.
 */
export async function pollAndDownload(pollUrl: string, fileUrl: string): Promise<void> {
  for (let i = 0; i < MAX_POLLS; i++) {
    const response = await apiClient.get<{ status: string; error_message?: string }>(pollUrl);
    const { status, error_message } = response.data;

    if (status === 'succeeded') {
      // Reason: derive a sensible filename from the URL, falling back to 'download'
      const segments = fileUrl.split('/');
      const derivedFilename = segments[segments.length - 1] || 'download';
      await downloadBlob(fileUrl, derivedFilename);
      return;
    }

    if (status === 'failed') {
      throw new Error(error_message ?? 'Export job failed');
    }

    await sleep(POLL_INTERVAL_MS);
  }

  throw new Error('Export timed out after 5 minutes');
}
