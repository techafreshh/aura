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

export const uploadResume = async (file: File, jobDescription?: string): Promise<UploadResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  if (jobDescription && jobDescription.trim()) {
    formData.append('job_description', jobDescription.trim());
  }
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


// ---------------------------------------------------------------- Invites

export interface InviteOut {
  invite_id: string;
  title: string;
  context: string | null;
  questions: string[];
  token: string;
  status: 'pending' | 'completed' | 'cancelled';
  created_at: string;
  completed_at: string | null;
  // When the link stops being redeemable; null = no expiry (legacy invites).
  expires_at: string | null;
  candidate_user_id: string | null;
  session_id: string | null;
  candidate_name: string | null;
  overall_score: number | null;
  recommendation: 'Hire' | 'No Hire' | 'Strong Hire' | 'Hold' | null;
}

export interface RecruiterInvitesResponse {
  invites: InviteOut[];
  quota_used: number;
  quota_limit: number;
}

export interface InviteDetail extends InviteOut {
  report: FinalReport | null;
  transcript: TranscriptEntryRead[] | null;
}

export interface InvitePreview {
  title: string;
  context: string | null;
  questions: string[];
  recruiter_name: string;
  expires_at: string | null;
}

export interface InviteStartResponse {
  session_id: string;
  plan: InterviewPlan;
}

export interface InviteCreatePayload {
  title: string;
  context?: string;
  questions: string[];
  /** Hours the link stays redeemable (1–720). Omitted = the API's 24h default. */
  expires_in_hours?: number;
}

export const createInvite = async (payload: InviteCreatePayload): Promise<InviteOut> => {
  const response = await api.post<InviteOut>('/recruiter/invites', payload);
  return response.data;
};

export const listRecruiterInvites = async (): Promise<RecruiterInvitesResponse> => {
  const response = await api.get<RecruiterInvitesResponse>('/recruiter/invites');
  return response.data;
};

export const getRecruiterInvite = async (inviteId: string): Promise<InviteDetail> => {
  const response = await api.get<InviteDetail>(`/recruiter/invites/${inviteId}`);
  return response.data;
};

export const cancelInvite = async (inviteId: string): Promise<InviteOut> => {
  const response = await api.post<InviteOut>(`/recruiter/invites/${inviteId}/cancel`);
  return response.data;
};

export const getInvitePreview = async (token: string): Promise<InvitePreview> => {
  const response = await api.get<InvitePreview>(`/invite/${token}`);
  return response.data;
};

export const startInvite = async (token: string): Promise<InviteStartResponse> => {
  const response = await api.post<InviteStartResponse>(`/invite/${token}/start`);
  return response.data;
};

export const uploadAudio = async (sessionId: string, blob: Blob, ext: 'webm' | 'mp4'): Promise<void> => {
  const formData = new FormData();
  formData.append('file', blob, `audio.${ext}`);
  await api.post(`/audio/${sessionId}`, formData);
};

export const setUserRole = async (role: 'candidate' | 'recruiter'): Promise<{ token: string; user: { id: string; email: string; name: string; role: string; avatar_url?: string | null } }> => {
  const response = await api.post('/auth/role', { role });
  return response.data;
};

/** Fetch a protected artifact as a blob (plain links cannot carry the JWT header). */
export const fetchBlob = async (path: string): Promise<Blob> => {
  const response = await api.get(path, { responseType: 'blob' });
  return response.data;
};

/** Download a protected artifact via authenticated fetch + anchor click. */
export const downloadFile = async (path: string, filename: string): Promise<void> => {
  const blob = await fetchBlob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};
