import apiClient from './client';
import type {
  Organization,
  OrganizationMember,
  OrganizationInvite,
  UserSearchResult,
} from '../types';

export interface OrganizationCreateRequest {
  name: string;
}

export interface OrganizationMemberAddRequest {
  user_id: string;
  role: 'viewer' | 'intern' | 'lawyer' | 'owner';
}

export interface OrganizationInviteRequest {
  email: string;
  role: 'viewer' | 'intern' | 'lawyer' | 'owner';
  expires_in_days?: number;
}

export const orgsApi = {
  list: async (): Promise<Organization[]> => {
    const response = await apiClient.get<Organization[]>('/api/v1/orgs');
    return response.data;
  },
  get: async (orgId: string): Promise<Organization> => {
    const response = await apiClient.get<Organization>(`/api/v1/orgs/${orgId}`);
    return response.data;
  },
  create: async (payload: OrganizationCreateRequest): Promise<Organization> => {
    const response = await apiClient.post<Organization>('/api/v1/orgs', payload);
    return response.data;
  },
  listMembers: async (orgId: string): Promise<OrganizationMember[]> => {
    const response = await apiClient.get<OrganizationMember[]>(`/api/v1/orgs/${orgId}/members`);
    return response.data;
  },
  addMember: async (orgId: string, payload: OrganizationMemberAddRequest): Promise<OrganizationMember> => {
    const response = await apiClient.post<OrganizationMember>(`/api/v1/orgs/${orgId}/members`, payload);
    return response.data;
  },
  invite: async (orgId: string, payload: OrganizationInviteRequest): Promise<OrganizationInvite> => {
    const response = await apiClient.post<OrganizationInvite>(`/api/v1/orgs/${orgId}/invites`, payload);
    return response.data;
  },
  acceptInvite: async (token: string): Promise<{ organization_id: string; role: string; status: string }> => {
    const response = await apiClient.post(`/api/v1/invites/${token}/accept`);
    return response.data;
  },
  searchUsers: async (q: string): Promise<UserSearchResult[]> => {
    const response = await apiClient.get<UserSearchResult[]>('/api/v1/users/search', { params: { q } });
    return response.data;
  },
};

export default orgsApi;
