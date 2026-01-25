import apiClient from './client';
import type { EntityUsageSummary } from '../types';

export const usageApi = {
  list: async (caseId: string, entityType?: string): Promise<EntityUsageSummary[]> => {
    const response = await apiClient.get<EntityUsageSummary[]>(`/api/v1/cases/${caseId}/usage`, {
      params: entityType ? { entity_type: entityType } : undefined,
    });
    return response.data;
  },
};

export default usageApi;
