import { describe, it, expect } from 'vitest';
import { theme } from '../../../src/styles/theme';

describe('theme', () => {
  it('has brandPrimary[6] equal to #1B4F8A', () => {
    expect(theme.colors!.brandPrimary![6].toLowerCase()).toBe('#1b4f8a');
  });

  it('has statusUploaded[6] equal to #16A34A', () => {
    expect(theme.colors!.statusUploaded![6].toLowerCase()).toBe('#16a34a');
  });

  it('has statusNotUploaded[6] equal to #6B7280', () => {
    expect(theme.colors!.statusNotUploaded![6].toLowerCase()).toBe('#6b7280');
  });

  it('has statusResubmit[6] equal to #D97706', () => {
    expect(theme.colors!.statusResubmit![6].toLowerCase()).toBe('#d97706');
  });

  it('has statusOverdue[6] equal to #DC2626', () => {
    expect(theme.colors!.statusOverdue![6].toLowerCase()).toBe('#dc2626');
  });
});
