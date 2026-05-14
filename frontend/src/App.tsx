import { useState } from 'react'
import { useInterview } from './hooks/use-interview'
import { uploadResume, getToken } from './api/client'
import { InterviewAgent } from './components/voice/InterviewAgent'
import { ReportView } from './components/interview/ReportView'
import { Button } from './components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from './components/ui/card'
import { Input } from './components/ui/input'
import { Toaster } from './components/ui/toaster'
import { useToast } from './hooks/use-toast'
import { Loader2, Upload, Play, CheckCircle2 } from 'lucide-react'

function App() {
  const { step, sessionId, plan, report, startPreview, startInterview, showReport, reset } = useInterview()
  const [file, setFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [token, setToken] = useState<string | null>(null)
  const [isConnecting, setIsConnecting] = useState(false)
  const { toast } = useToast()

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
    }
  }

  const handleUpload = async () => {
    if (!file) return
    setIsUploading(true)
    try {
      console.log("Starting upload for file:", file.name);
      const data = await uploadResume(file)
      console.log("Upload successful, received data:", data);
      startPreview(data)
      toast({
        title: "Resume parsed successfully!",
        description: `Ready to interview ${data.plan_summary.candidate_name}`,
      })
    } catch (error) {
      console.error("Upload failed with error:", error);
      toast({
        title: "Upload failed",
        description: error instanceof Error ? error.message : "Please make sure you are uploading a valid PDF.",
        variant: "destructive",
      })
    } finally {
      setIsUploading(false)
    }
  }

  const handleJoin = async () => {
    if (!sessionId) return
    setIsConnecting(true)
    try {
      const token = await getToken(sessionId)
      setToken(token)
      startInterview()
    } catch (error) {
      toast({
        title: "Connection failed",
        description: "Could not retrieve access token from server.",
        variant: "destructive",
      })
    } finally {
      setIsConnecting(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <header className="border-b bg-white dark:bg-slate-900 px-6 py-4">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <h1 className="text-xl font-bold tracking-tight">AI Interviewer Agent</h1>
          {step !== 'UPLOAD' && (
            <Button variant="ghost" size="sm" onClick={reset}>
              Exit
            </Button>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto p-6 h-[calc(100vh-73px)]">
        {step === 'UPLOAD' && (
          <div className="h-full flex items-center justify-center">
            <Card className="w-full max-w-md">
              <CardHeader>
                <CardTitle>Welcome</CardTitle>
                <CardDescription>Upload your resume to begin your AI-led interview.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="border-2 border-dashed rounded-lg p-8 text-center space-y-4 border-slate-200 dark:border-slate-800">
                  <Upload className="mx-auto h-12 w-12 text-slate-400" />
                  <div className="space-y-1">
                    <p className="text-sm font-medium">Click to upload or drag and drop</p>
                    <p className="text-xs text-slate-500">PDF only (max 10MB)</p>
                  </div>
                  <Input 
                    type="file" 
                    accept=".pdf" 
                    className="cursor-pointer" 
                    onChange={handleFileChange}
                  />
                  {file && (
                    <p className="text-sm text-green-600 font-medium flex items-center justify-center gap-1">
                      <CheckCircle2 className="h-4 w-4" /> {file.name}
                    </p>
                  )}
                </div>
              </CardContent>
              <CardFooter>
                <Button 
                  className="w-full" 
                  disabled={!file || isUploading} 
                  onClick={handleUpload}
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Parsing Resume...
                    </>
                  ) : (
                    "Prepare Interview"
                  )}
                </Button>
              </CardFooter>
            </Card>
          </div>
        )}

        {step === 'PREVIEW' && plan && (
          <div className="h-full flex items-center justify-center">
            <Card className="w-full max-w-2xl">
              <CardHeader>
                <CardTitle>Interview Ready: {plan.candidate_name}</CardTitle>
                <CardDescription>We've prepared a customized interview based on your background.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold">Identified Skills</h4>
                  <div className="flex flex-wrap gap-2">
                    {plan.extracted_skills.map((skill, i) => (
                      <span key={i} className="px-2 py-1 bg-slate-100 dark:bg-slate-800 rounded text-xs">
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold">Focus Areas</h4>
                  <ul className="text-sm text-slate-600 dark:text-slate-400 space-y-1 list-disc list-inside">
                    {plan.question_bank.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                </div>
              </CardContent>
              <CardFooter className="flex gap-3">
                <Button variant="outline" className="flex-1" onClick={reset}>
                  Cancel
                </Button>
                <Button className="flex-1" onClick={handleJoin} disabled={isConnecting}>
                  {isConnecting ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Connecting...
                    </>
                  ) : (
                    <>
                      <Play className="mr-2 h-4 w-4" />
                      Start Voice Interview
                    </>
                  )}
                </Button>
              </CardFooter>
            </Card>
          </div>
        )}

        {step === 'INTERVIEW' && token && sessionId && (
          <InterviewAgent 
            token={token} 
            sessionId={sessionId} 
            onInterviewEnd={showReport} 
          />
        )}

        {step === 'REPORT' && report && (
          <ReportView report={report} onDone={reset} />
        )}
      </main>
      <Toaster />
    </div>
  )
}

export default App
