import apiClient from './client';

export interface UserLookupResult {
  id: string;
  email: string;
  name: string;
  system_role: string;
  firm_id: string;
  professional_role?: string;
}

export interface FirmUser {
  id: string;
  email: string;
  name: string;
  system_role: 'super_admin' | 'admin' | 'member' | 'viewer';
  professional_role?: string;
  is_active: boolean;
  last_login?: string;
}

export interface CreateUserRequest {
  email: string;
  name: string;
  system_role?: string;
  professional_role?: string;
}

export const usersApi = {
  // Lookup user by email
  lookupByEmail: async (email: string): Promise<UserLookupResult> => {
    const response = await apiClient.get<UserLookupResult>('/users/by-email', {
      params: { email },
    });
    return response.data;
  },

  // List users in firm
  list: async (activeOnly = true): Promise<FirmUser[]> => {
    const response = await apiClient.get<FirmUser[]>('/users', {
      params: { active_only: activeOnly },
    });
    return response.data;
  },

  // Create new user
  create: async (data: CreateUserRequest): Promise<FirmUser> => {
    const response = await apiClient.post<FirmUser>('/users', data);
    return response.data;
  },

  // Get user by ID
  get: async (userId: string): Promise<FirmUser> => {
    const response = await apiClient.get<FirmUser>(`/users/${userId}`);
    return response.data;
  },
};

export default usersApi;
