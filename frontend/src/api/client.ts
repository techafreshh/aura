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

export const getDownloadUrl = (sessionId: string, fileType: 'pdf' | 'transcript'): string => {
  return `${BASE_URL}/download/${sessionId}/${fileType}`;
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

export default api;
