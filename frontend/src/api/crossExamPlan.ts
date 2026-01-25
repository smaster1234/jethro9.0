import apiClient from './client';
import type { CrossExamPlanResponse, WitnessSimulationResponse } from '../types';

export interface CrossExamPlanRequest {
  contradiction_ids?: string[];
  witness_id?: string;
}

export interface WitnessSimulationRequest {
  persona: 'cooperative' | 'evasive' | 'hostile';
  plan_id?: string;
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
  simulateWitness: async (runId: string, data: WitnessSimulationRequest): Promise<WitnessSimulationResponse> => {
    const response = await apiClient.post<WitnessSimulationResponse>(
      `/api/v1/analysis-runs/${runId}/witness-simulation`,
      data
    );
    return response.data;
  },
  exportPlan: async (runId: string, format: 'docx' | 'pdf'): Promise<Blob> => {
    const response = await apiClient.get(`/api/v1/analysis-runs/${runId}/export/cross-exam`, {
      params: { format },
      responseType: 'blob',
    });
    return response.data as Blob;
  },
};

export default crossExamPlanApi;
