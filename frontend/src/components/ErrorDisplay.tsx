import { useState } from 'react';
import { Alert, Text, Code, Collapse, Table, Button, Stack } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { AxiosError } from 'axios';

/** Row-level validation error detail from the backend. */
interface ApiErrorDetails {
  row?: number;
  column?: string;
  code: string;
  reason: string;
}

/** Backend error envelope shape. */
interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: ApiErrorDetails[];
  };
  request_id?: string;
}

/**
 * Props for the ErrorDisplay component.
 */
interface ErrorDisplayProps {
  /** The error to display. Can be an AxiosError, generic Error, null, or undefined. */
  error: AxiosError<ApiErrorEnvelope> | Error | null | undefined;
}

/** Maximum number of detail rows to render in the collapsible table. */
const MAX_DETAIL_ROWS = 100;

/**
 * Type guard to check if an error is an AxiosError with response data.
 *
 * @param error - The error to check.
 * @returns Whether the error is an AxiosError.
 */
function isAxiosError(error: unknown): error is AxiosError<ApiErrorEnvelope> {
  return error instanceof Error && 'isAxiosError' in error;
}

/**
 * Type guard to check if response data matches the ApiErrorEnvelope shape.
 *
 * @param data - The response data to check.
 * @returns Whether the data is a valid error envelope.
 */
function isErrorEnvelope(data: unknown): data is ApiErrorEnvelope {
  return (
    typeof data === 'object' &&
    data !== null &&
    'error' in data &&
    typeof (data as ApiErrorEnvelope).error?.code === 'string' &&
    typeof (data as ApiErrorEnvelope).error?.message === 'string'
  );
}

/**
 * ErrorDisplay renders the backend error envelope using Mantine Alert.
 * Handles network errors, validation errors with optional row-level details,
 * and generic HTTP errors gracefully.
 *
 * @param props - The component props.
 * @returns The error display UI, or null if no error.
 */
export function ErrorDisplay({ error }: ErrorDisplayProps) {
  const { t } = useTranslation();
  const [detailsOpen, setDetailsOpen] = useState(false);

  if (!error) {
    return null;
  }

  // Case 2: Network error (no response)
  if (!isAxiosError(error) || !error.response) {
    return (
      <Alert color="red" title={t('errors.network_error')}>
        <Text>{error.message}</Text>
      </Alert>
    );
  }

  const responseData = error.response.data;

  // Case 3: Parseable error envelope
  if (isErrorEnvelope(responseData)) {
    const { code, message, details } = responseData.error;
    const requestId = responseData.request_id;
    const hasDetails = details && details.length > 0;

    return (
      <Alert color="red" title={<Code>{code}</Code>}>
        <Stack gap="xs">
          <Text>{message}</Text>
          {requestId && (
            <Text size="xs" c="dimmed">
              Request ID: {requestId}
            </Text>
          )}
          {hasDetails && (
            <>
              <Button
                variant="subtle"
                size="xs"
                onClick={() => setDetailsOpen((o) => !o)}
                aria-expanded={detailsOpen}
              >
                {detailsOpen ? t('errors.hide_details') : t('errors.show_details')}
              </Button>
              <Collapse in={detailsOpen}>
                <Table striped>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t('errors.detail_row')}</Table.Th>
                      <Table.Th>{t('errors.detail_column')}</Table.Th>
                      <Table.Th>{t('errors.detail_code')}</Table.Th>
                      <Table.Th>{t('errors.detail_reason')}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {details.slice(0, MAX_DETAIL_ROWS).map((d, idx) => (
                      <Table.Tr key={idx}>
                        <Table.Td>{d.row ?? '-'}</Table.Td>
                        <Table.Td>{d.column ?? '-'}</Table.Td>
                        <Table.Td>
                          <Code>{d.code}</Code>
                        </Table.Td>
                        <Table.Td>{d.reason}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
                {details.length > MAX_DETAIL_ROWS && (
                  <Text size="sm" c="dimmed" mt="xs">
                    {t('errors.remaining_errors', { count: details.length - MAX_DETAIL_ROWS })}
                  </Text>
                )}
              </Collapse>
            </>
          )}
        </Stack>
      </Alert>
    );
  }

  // Case 4: AxiosError with no parseable body
  return (
    <Alert color="red" title={t('common.error')}>
      <Text>{t('errors.generic_http', { status: error.response.status })}</Text>
    </Alert>
  );
}
