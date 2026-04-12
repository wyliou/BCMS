import { z } from 'zod';
import { apiClient } from './client';

/**
 * Zod schema for a failed notification item.
 */
const FailedNotificationItemSchema = z.object({
  id: z.string(),
  type: z.string(),
  recipient_id: z.string(),
  status: z.string(),
  bounce_reason: z.string().nullable(),
  created_at: z.string(),
});

export type FailedNotificationItem = z.infer<typeof FailedNotificationItemSchema>;

/**
 * Zod schema for the failed notifications list response.
 */
const FailedNotificationsResponseSchema = z.object({
  items: z.array(FailedNotificationItemSchema),
});

export type FailedNotificationsResponse = z.infer<typeof FailedNotificationsResponseSchema>;

/**
 * Zod schema for the resend notification response.
 */
const ResendResponseSchema = z.object({
  id: z.string(),
  status: z.string(),
  bounce_reason: z.string().nullable().optional(),
});

export type ResendResponse = z.infer<typeof ResendResponseSchema>;

/**
 * Zod schema for a resubmit request record.
 */
const ResubmitRequestReadSchema = z.object({
  id: z.string().uuid(),
  cycle_id: z.string().uuid(),
  org_unit_id: z.string().uuid(),
  requester_id: z.string().uuid(),
  target_version: z.number().int().nullable(),
  reason: z.string(),
  requested_at: z.string(),
});

export type ResubmitRequestRead = z.infer<typeof ResubmitRequestReadSchema>;

/**
 * Payload for creating a resubmit request.
 */
export interface CreateResubmitRequestPayload {
  cycle_id: string;
  org_unit_id: string;
  reason: string;
  target_version?: number;
  requester_user_id: string;
  recipient_user_id: string;
  recipient_email: string;
}

/**
 * Fetches the list of failed notifications (global, not cycle-scoped).
 *
 * @returns The list of failed notification items.
 */
export async function listFailedNotifications(): Promise<FailedNotificationsResponse> {
  const response = await apiClient.get<unknown>('/notifications/failed');
  return FailedNotificationsResponseSchema.parse(response.data);
}

/**
 * Resends a failed notification to a specified email.
 *
 * @param notificationId - The notification ID to resend.
 * @param recipientEmail - The email address to send to.
 * @returns The resend result.
 */
export async function resendNotification(
  notificationId: string,
  recipientEmail: string,
): Promise<ResendResponse> {
  const response = await apiClient.post<unknown>(`/notifications/${notificationId}/resend`, {
    recipient_email: recipientEmail,
  });
  return ResendResponseSchema.parse(response.data);
}

/**
 * Creates a resubmit request for a filing unit.
 * The backend persists the record and sends an email notification.
 *
 * @param payload - The resubmit request payload including cycle, org unit, and reason.
 * @returns The created ResubmitRequestRead record.
 */
export async function createResubmitRequest(
  payload: CreateResubmitRequestPayload,
): Promise<ResubmitRequestRead> {
  const response = await apiClient.post<unknown>('/resubmit-requests', payload);
  return ResubmitRequestReadSchema.parse(response.data);
}

/**
 * Fetches all resubmit requests for a given cycle and org unit.
 *
 * @param cycleId - The cycle UUID.
 * @param orgUnitId - The org unit UUID.
 * @returns Array of ResubmitRequestRead records.
 */
export async function listResubmitRequests(
  cycleId: string,
  orgUnitId: string,
): Promise<ResubmitRequestRead[]> {
  const response = await apiClient.get<unknown>('/resubmit-requests', {
    params: { cycle_id: cycleId, org_unit_id: orgUnitId },
  });
  return z.array(ResubmitRequestReadSchema).parse(response.data);
}
