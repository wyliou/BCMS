import { describe, it, expect } from 'vitest';
import i18n from '../../../src/i18n';

describe('i18n', () => {
  it('returns the loading string for common.loading', () => {
    expect(i18n.t('common.loading')).toBe('載入中...');
  });

  it('has zh-TW as the default language', () => {
    expect(i18n.language).toBe('zh-TW');
  });

  it('returns the key string for a missing key', () => {
    expect(i18n.t('nonexistent.key.here')).toBe('nonexistent.key.here');
  });

  it('returns the correct status label for not_uploaded', () => {
    expect(i18n.t('status.not_uploaded')).toBe('未上傳');
  });

  it('returns the correct nav label for dashboard', () => {
    expect(i18n.t('nav.dashboard')).toBe('儀表板');
  });
});
