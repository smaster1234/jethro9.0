import apiClient from './client';
import type { Document, Folder, UploadResponse, Job, DocumentUploadMetadata } from '../types';

export interface ListDocumentsParams {
  status?: string;
  party?: string;
  role?: string;
  folder_id?: string;
}

export interface SnippetResponse {
  doc_id: string;
  doc_name: string;
  page_no: number;
  block_index: number;
  text: string;
  context_before?: string;
  context_after?: string;
}

export const documentsApi = {
  // List documents in a case
  list: async (caseId: string, params?: ListDocumentsParams): Promise<Document[]> => {
    const response = await apiClient.get<Document[]>(`/api/v1/cases/${caseId}/documents`, {
      params,
    });
    return response.data;
  },

  // Get document by ID
  get: async (docId: string): Promise<Document> => {
    const response = await apiClient.get<Document>(`/api/v1/documents/${docId}`);
    return response.data;
  },

  // Get document text
  getText: async (docId: string): Promise<{ doc_id: string; doc_name: string; text: string; page_count: number }> => {
    const response = await apiClient.get(`/api/v1/documents/${docId}/text`);
    return response.data;
  },

  // Get document snippet (for "show source")
  getSnippet: async (
    docId: string,
    pageNo: number,
    blockIndex: number,
    context = 1
  ): Promise<SnippetResponse> => {
    const response = await apiClient.get<SnippetResponse>(`/api/v1/documents/${docId}/snippet`, {
      params: { page_no: pageNo, block_index: blockIndex, context },
    });
    return response.data;
  },

  // Upload documents
  upload: async (
    caseId: string,
    files: File[],
    metadata: DocumentUploadMetadata[],
    folderId?: string
  ): Promise<UploadResponse> => {
    const formData = new FormData();

    files.forEach((file) => {
      formData.append('files', file);
    });

    formData.append('metadata_json', JSON.stringify(metadata));

    if (folderId) {
      formData.append('folder_id', folderId);
    }

    const response = await apiClient.post<UploadResponse>(
      `/api/v1/cases/${caseId}/documents`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  },

  // Upload ZIP archive
  uploadZip: async (
    caseId: string,
    file: File,
    baseFolderId?: string,
    mappingMode = 'auto'
  ): Promise<{ job_id: string; message: string }> => {
    const formData = new FormData();
    formData.append('file', file);

    if (baseFolderId) {
      formData.append('base_folder_id', baseFolderId);
    }
    formData.append('mapping_mode', mappingMode);

    const response = await apiClient.post(
      `/api/v1/cases/${caseId}/documents/zip`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  },

  // Get job status
  getJobStatus: async (jobId: string): Promise<Job> => {
    const response = await apiClient.get<Job>(`/api/v1/jobs/${jobId}`);
    return response.data;
  },

  // Folder operations
  folders: {
    // Create folder
    create: async (caseId: string, name: string, parentId?: string): Promise<Folder> => {
      const response = await apiClient.post<Folder>(`/api/v1/cases/${caseId}/folders`, {
        name,
        parent_id: parentId,
      });
      return response.data;
    },

    // Get folder tree
    getTree: async (caseId: string): Promise<Folder[]> => {
      const response = await apiClient.get<Folder[]>(`/api/v1/cases/${caseId}/folders/tree`);
      return response.data;
    },

    // List documents in folder
    listDocuments: async (folderId: string, params?: Omit<ListDocumentsParams, 'folder_id'>): Promise<Document[]> => {
      const response = await apiClient.get<Document[]>(`/api/v1/folders/${folderId}/documents`, {
        params,
      });
      return response.data;
    },
  },
};

export default documentsApi;
