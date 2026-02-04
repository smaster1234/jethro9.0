import apiClient from './client';
import type { EvidenceAnchor, AnchorResolveResponse } from '../types';

export interface AnchorResolveRequest {
  anchor: EvidenceAnchor;
  context?: number;
}

export const anchorsApi = {
  resolve: async (data: AnchorResolveRequest): Promise<AnchorResolveResponse> => {
    const response = await apiClient.post<AnchorResolveResponse>('/api/v1/anchors/resolve', data);
    return response.data;
  },
};

export default anchorsApi;
