import apiClient, { setTokens, clearTokens } from './client';
import type { LoginRequest, RegisterRequest, TokenResponse, User } from '../types';

export interface UpdateProfileRequest {
  name?: string;
  professional_role?: string;
}

export interface UpdateProfileResponse {
  id: string;
  email: string;
  name: string;
  professional_role?: string;
  message: string;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ForgotPasswordResponse {
  message: string;
  _dev_token?: string;  // Only in development mode
  _dev_note?: string;
}

export interface ResetPasswordRequest {
  token: string;
  new_password: string;
}

export interface ResetPasswordResponse {
  message: string;
}

export const authApi = {
  // Login with email and password
  login: async (data: LoginRequest): Promise<TokenResponse> => {
    const response = await apiClient.post<TokenResponse>('/auth/login', data);
    setTokens(response.data);
    return response.data;
  },

  // Register new user
  register: async (data: RegisterRequest): Promise<TokenResponse> => {
    const response = await apiClient.post<TokenResponse>('/auth/register', data);
    setTokens(response.data);
    return response.data;
  },

  // Get current user info
  me: async (): Promise<User> => {
    const response = await apiClient.get<User>('/auth/me');
    return response.data;
  },

  // Get user by email (demo mode)
  getUserByEmail: async (email: string): Promise<User> => {
    const response = await apiClient.get<User>('/users/by-email', {
      params: { email },
    });
    return response.data;
  },

  // Update user profile
  updateProfile: async (data: UpdateProfileRequest): Promise<UpdateProfileResponse> => {
    const response = await apiClient.patch<UpdateProfileResponse>('/users/me', data);
    return response.data;
  },

  // Logout
  logout: () => {
    clearTokens();
  },

  // Request password reset
  forgotPassword: async (data: ForgotPasswordRequest): Promise<ForgotPasswordResponse> => {
    const response = await apiClient.post<ForgotPasswordResponse>('/auth/forgot-password', data);
    return response.data;
  },

  // Reset password with token
  resetPassword: async (data: ResetPasswordRequest): Promise<ResetPasswordResponse> => {
    const response = await apiClient.post<ResetPasswordResponse>('/auth/reset-password', data);
    return response.data;
  },
};

export default authApi;
