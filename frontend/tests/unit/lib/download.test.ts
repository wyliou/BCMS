import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../../setup';
import { downloadBlob, pollAndDownload } from '../../../src/lib/download';

describe('downloadBlob', () => {
  let originalCreateObjectURL: typeof URL.createObjectURL;
  let originalRevokeObjectURL: typeof URL.revokeObjectURL;

  beforeEach(() => {
    originalCreateObjectURL = URL.createObjectURL;
    originalRevokeObjectURL = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn().mockReturnValue('blob:test-url');
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    vi.restoreAllMocks();
  });

  it('creates object URL, clicks anchor, and revokes URL', async () => {
    const fakeBlob = new Blob(['test'], { type: 'application/octet-stream' });
    server.use(
      http.get('*/download/test-file', () => {
        return new HttpResponse(fakeBlob);
      }),
    );

    const clickSpy = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = originalCreateElement(tag);
      if (tag === 'a') {
        vi.spyOn(el, 'click').mockImplementation(clickSpy);
      }
      return el;
    });

    await downloadBlob('/download/test-file', 'test.xlsx');

    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-url');
  });

  it('sets the correct filename on the anchor download attribute', async () => {
    const fakeBlob = new Blob(['test']);
    server.use(
      http.get('*/download/file2', () => {
        return new HttpResponse(fakeBlob);
      }),
    );

    let capturedDownload = '';
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = originalCreateElement(tag);
      if (tag === 'a') {
        // Reason: Capture the download attribute before click
        vi.spyOn(el, 'click').mockImplementation(() => {
          capturedDownload = (el as HTMLAnchorElement).download;
        });
      }
      return el;
    });

    await downloadBlob('/download/file2', 'report.xlsx');
    expect(capturedDownload).toBe('report.xlsx');
  });
});

describe('pollAndDownload', () => {
  let originalCreateObjectURL: typeof URL.createObjectURL;
  let originalRevokeObjectURL: typeof URL.revokeObjectURL;

  beforeEach(() => {
    originalCreateObjectURL = URL.createObjectURL;
    originalRevokeObjectURL = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn().mockReturnValue('blob:test-url');
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    vi.restoreAllMocks();
  });

  /**
   * Mocks document.createElement to capture and suppress anchor clicks.
   */
  function mockAnchorClick() {
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = originalCreateElement(tag);
      if (tag === 'a') {
        vi.spyOn(el, 'click').mockImplementation(() => {});
      }
      return el;
    });
  }

  it('downloads immediately when job succeeds on first poll', async () => {
    const fakeBlob = new Blob(['data']);
    server.use(
      http.get('*/exports/job1/status', () => {
        return HttpResponse.json({ status: 'succeeded' });
      }),
      http.get('*/exports/job1/file', () => {
        return new HttpResponse(fakeBlob);
      }),
    );

    mockAnchorClick();
    await pollAndDownload('/exports/job1/status', '/exports/job1/file');
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it('polls multiple times until succeeded', async () => {
    let pollCount = 0;
    const fakeBlob = new Blob(['data']);

    server.use(
      http.get('*/exports/job2/status', () => {
        pollCount++;
        if (pollCount < 3) {
          return HttpResponse.json({ status: 'running' });
        }
        return HttpResponse.json({ status: 'succeeded' });
      }),
      http.get('*/exports/job2/file', () => {
        return new HttpResponse(fakeBlob);
      }),
    );

    mockAnchorClick();
    await pollAndDownload('/exports/job2/status', '/exports/job2/file');
    expect(pollCount).toBe(3);
  });

  it('rejects when job status is failed', async () => {
    server.use(
      http.get('*/exports/job3/status', () => {
        return HttpResponse.json({ status: 'failed', error_message: 'Export error' });
      }),
    );

    await expect(
      pollAndDownload('/exports/job3/status', '/exports/job3/file'),
    ).rejects.toThrow('Export error');
  });
});
