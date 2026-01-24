import { useCallback } from 'react';
import { useToast } from '../components/ui/Toast';
import { handleApiError } from '../api/client';

/**
 * Hook that provides API call wrappers with automatic toast notifications.
 *
 * Usage:
 * const { withErrorToast, withSuccessToast } = useApiWithToast();
 *
 * // Show error toast on failure
 * const data = await withErrorToast(casesApi.create(newCase), 'Failed to create case');
 *
 * // Show success toast on success
 * await withSuccessToast(casesApi.delete(id), 'Case deleted successfully');
 */
export function useApiWithToast() {
  const toast = useToast();

  /**
   * Wraps a promise and shows an error toast if it fails.
   */
  const withErrorToast = useCallback(
    async <T>(promise: Promise<T>, errorTitle?: string): Promise<T> => {
      try {
        return await promise;
      } catch (error) {
        const message = handleApiError(error);
        toast.error(errorTitle || 'שגיאה', message);
        throw error;
      }
    },
    [toast]
  );

  /**
   * Wraps a promise and shows a success toast when it completes.
   */
  const withSuccessToast = useCallback(
    async <T>(promise: Promise<T>, successTitle: string, successMessage?: string): Promise<T> => {
      try {
        const result = await promise;
        toast.success(successTitle, successMessage);
        return result;
      } catch (error) {
        const message = handleApiError(error);
        toast.error('שגיאה', message);
        throw error;
      }
    },
    [toast]
  );

  /**
   * Shows an error toast manually.
   */
  const showError = useCallback(
    (title: string, message?: string) => {
      toast.error(title, message);
    },
    [toast]
  );

  /**
   * Shows a success toast manually.
   */
  const showSuccess = useCallback(
    (title: string, message?: string) => {
      toast.success(title, message);
    },
    [toast]
  );

  /**
   * Shows a warning toast manually.
   */
  const showWarning = useCallback(
    (title: string, message?: string) => {
      toast.warning(title, message);
    },
    [toast]
  );

  /**
   * Shows an info toast manually.
   */
  const showInfo = useCallback(
    (title: string, message?: string) => {
      toast.info(title, message);
    },
    [toast]
  );

  return {
    withErrorToast,
    withSuccessToast,
    showError,
    showSuccess,
    showWarning,
    showInfo,
    toast,
  };
}

export default useApiWithToast;
