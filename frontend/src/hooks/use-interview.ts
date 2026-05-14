import { useState, useCallback } from 'react';
import type { UploadResponse, FinalReport, InterviewPlan } from '../api/client';

export type InterviewStep = 'UPLOAD' | 'PREVIEW' | 'INTERVIEW' | 'REPORT';

export function useInterview() {
  const [step, setStep] = useState<InterviewStep>('UPLOAD');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [plan, setPlan] = useState<InterviewPlan | null>(null);
  const [report, setReport] = useState<FinalReport | null>(null);

  const startPreview = useCallback((data: UploadResponse) => {
    setSessionId(data.session_id);
    setPlan(data.plan_summary);
    setStep('PREVIEW');
  }, []);

  const startInterview = useCallback(() => {
    setStep('INTERVIEW');
  }, []);

  const showReport = useCallback((finalReport: FinalReport) => {
    setReport(finalReport);
    setStep('REPORT');
  }, []);

  const reset = useCallback(() => {
    setStep('UPLOAD');
    setSessionId(null);
    setPlan(null);
    setReport(null);
  }, []);

  return {
    step,
    sessionId,
    plan,
    report,
    startPreview,
    startInterview,
    showReport,
    reset,
  };
}
