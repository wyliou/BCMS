import { Badge } from '@mantine/core';
import { useTranslation } from 'react-i18next';

/** Valid upload status values. */
type UploadStatus = 'not_uploaded' | 'uploaded' | 'resubmit' | 'overdue';

/**
 * Props for the StatusBadge component.
 */
interface StatusBadgeProps {
  /** The upload status to display. */
  status: UploadStatus;
}

/**
 * Maps upload status values to Mantine theme color keys.
 * Colors are defined in the theme — no hardcoded hex values here.
 */
const STATUS_COLOR_MAP: Record<UploadStatus, string> = {
  not_uploaded: 'statusNotUploaded',
  uploaded: 'statusUploaded',
  resubmit: 'statusResubmit',
  overdue: 'statusOverdue',
};

/**
 * Maps upload status values to i18n label keys.
 */
const STATUS_LABEL_MAP: Record<UploadStatus, string> = {
  not_uploaded: 'status.not_uploaded',
  uploaded: 'status.uploaded',
  resubmit: 'status.resubmit',
  overdue: 'status.overdue',
};

/**
 * StatusBadge renders a Mantine Badge with the correct color and
 * translated label for a given budget upload status.
 *
 * @param props - The component props.
 * @returns A colored badge representing the upload status.
 */
export function StatusBadge({ status }: StatusBadgeProps) {
  const { t } = useTranslation();

  return (
    <Badge color={STATUS_COLOR_MAP[status]} variant="filled">
      {t(STATUS_LABEL_MAP[status])}
    </Badge>
  );
}

export type { UploadStatus };
