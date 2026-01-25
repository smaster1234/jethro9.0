import apiClient from './client';
import type { CrossExamPlanResponse } from '../types';

export interface CrossExamPlanRequest {
  contradiction_ids?: string[];
  witness_id?: string;
}

export const crossExamPlanApi = {
  generate: async (runId: string, data: CrossExamPlanRequest): Promise<CrossExamPlanResponse> => {
    const response = await apiClient.post<CrossExamPlanResponse>(
      `/api/v1/analysis-runs/${runId}/cross-exam-plan`,
      data
    );
    return response.data;
  },
  getLatest: async (runId: string): Promise<CrossExamPlanResponse> => {
    const response = await apiClient.get<CrossExamPlanResponse>(
      `/api/v1/analysis-runs/${runId}/cross-exam-plan`
    );
    return response.data;
  },
};

export default crossExamPlanApi;
