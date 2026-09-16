import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('aura_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export interface InterviewPlan {
  candidate_name: string;
  extracted_skills: string[];
  question_bank: string[];
}

export interface UploadResponse {
  session_id: string;
  plan_summary: InterviewPlan;
}

export interface SectionGrade {
  section_name: string;
  score: number;
  comments: string;
}

export interface FinalReport {
  candidate_name: string;
  overall_score: number;
  section_grades: SectionGrade[];
  strengths: string[];
  weaknesses: string[];
  recommendation: 'Hire' | 'No Hire' | 'Strong Hire' | 'Hold';
  summary: string;
}

export const uploadResume = async (file: File): Promise<UploadResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post<UploadResponse>('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const getToken = async (sessionId: string): Promise<string> => {
  const response = await api.get<{ token: string }>(`/token?session_id=${sessionId}`);
  return response.data.token;
};

export const getPlan = async (sessionId: string): Promise<InterviewPlan> => {
  const response = await api.get<InterviewPlan>(`/plan/${sessionId}`);
  return response.data;
};

export const getReport = async (sessionId: string): Promise<FinalReport> => {
  const response = await api.get<FinalReport>(`/report/${sessionId}`);
  return response.data;
};

export const downloadArtifact = async (sessionId: string, fileType: 'pdf' | 'transcript'): Promise<void> => {
  const response = await api.get(`/download/${sessionId}/${fileType}`, { responseType: 'blob' });
  const url = URL.createObjectURL(response.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileType === 'pdf' ? 'report.pdf' : 'transcript.json';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

export const uploadPdf = async (sessionId: string, pdfBlob: Blob): Promise<void> => {
  const formData = new FormData();
  formData.append('file', pdfBlob, 'report.pdf');
  await api.post(`/upload-pdf/${sessionId}`, formData);
};

export interface SessionSummary {
  session_id: string;
  candidate_name: string;
  overall_score: number | null;
  recommendation: 'Hire' | 'No Hire' | 'Strong Hire' | 'Hold' | null;
  status: 'pending' | 'in_progress' | 'completed';
  created_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
}

export interface TranscriptEntryRead {
  speaker: string;
  text: string;
  timestamp_s: number;
}

export interface SessionDetail {
  session_id: string;
  candidate_name: string;
  user_email: string;
  user_id: string;
  plan: InterviewPlan | null;
  report: FinalReport | null;
  transcript: TranscriptEntryRead[] | null;
  status: 'pending' | 'in_progress' | 'completed';
  created_at: string;
  completed_at: string | null;
}

export const listAdminSessions = async (
  params: { status?: 'pending' | 'in_progress' | 'completed'; limit?: number; offset?: number } = {}
): Promise<SessionSummary[]> => {
  const response = await api.get<SessionSummary[]>('/admin/sessions', { params });
  return response.data;
};

export const listMySessions = async (): Promise<SessionSummary[]> => {
  const response = await api.get<SessionSummary[]>('/sessions/mine');
  return response.data;
};

export const getAdminSessionDetail = async (sessionId: string): Promise<SessionDetail> => {
  const response = await api.get<SessionDetail>(`/admin/sessions/${sessionId}/detail`);
  return response.data;
};

export const getMySessionDetail = async (sessionId: string): Promise<SessionDetail> => {
  const response = await api.get<SessionDetail>(`/sessions/${sessionId}/detail`);
  return response.data;
};

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'candidate';
  avatar_url?: string | null;
}

export interface LoginResponse {
  token: string;
  user: AuthUser;
}

/** Pull a human-readable message out of an axios error from our API. */
export const apiErrorMessage = (error: unknown, fallback = 'Something went wrong. Please try again.'): string => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (detail?.message) return detail.message as string;
  }
  return fallback;
};

export const registerUser = async (email: string, password: string, name: string): Promise<{ message: string }> => {
  const response = await api.post<{ message: string }>('/auth/register', { email, password, name });
  return response.data;
};

export const loginWithPassword = async (email: string, password: string): Promise<LoginResponse> => {
  const response = await api.post<LoginResponse>('/auth/login', { email, password });
  return response.data;
};

export const resendVerification = async (email: string): Promise<{ message: string }> => {
  const response = await api.post<{ message: string }>('/auth/resend-verification', { email });
  return response.data;
};

export const requestPasswordReset = async (email: string): Promise<{ message: string }> => {
  const response = await api.post<{ message: string }>('/auth/forgot-password', { email });
  return response.data;
};

export const resetPassword = async (token: string, newPassword: string): Promise<{ message: string }> => {
  const response = await api.post<{ message: string }>('/auth/reset-password', {
    token,
    new_password: newPassword,
  });
  return response.data;
};

export default api;
