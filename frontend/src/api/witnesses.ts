import apiClient from './client';
import type { Witness, WitnessVersion, WitnessVersionDiffResponse } from '../types';

export interface CreateWitnessRequest {
  name: string;
  side?: string;
  extra_data?: Record<string, unknown>;
}

export interface CreateWitnessVersionRequest {
  document_id: string;
  version_type?: string;
  version_date?: string;
  extra_data?: Record<string, unknown>;
}

export interface WitnessDiffRequest {
  version_a_id: string;
  version_b_id: string;
}

export const witnessesApi = {
  list: async (caseId: string): Promise<Witness[]> => {
    const response = await apiClient.get<Witness[]>(`/api/v1/cases/${caseId}/witnesses`, {
      params: { include_versions: true },
    });
    return response.data;
  },
  create: async (caseId: string, data: CreateWitnessRequest): Promise<Witness> => {
    const response = await apiClient.post<Witness>(`/api/v1/cases/${caseId}/witnesses`, data);
    return response.data;
  },
  listVersions: async (witnessId: string): Promise<WitnessVersion[]> => {
    const response = await apiClient.get<WitnessVersion[]>(`/api/v1/witnesses/${witnessId}/versions`);
    return response.data;
  },
  createVersion: async (witnessId: string, data: CreateWitnessVersionRequest): Promise<WitnessVersion> => {
    const response = await apiClient.post<WitnessVersion>(`/api/v1/witnesses/${witnessId}/versions`, data);
    return response.data;
  },
  diffVersions: async (witnessId: string, data: WitnessDiffRequest): Promise<WitnessVersionDiffResponse> => {
    const response = await apiClient.post<WitnessVersionDiffResponse>(
      `/api/v1/witnesses/${witnessId}/versions/diff`,
      data
    );
    return response.data;
  },
};

export default witnessesApi;
