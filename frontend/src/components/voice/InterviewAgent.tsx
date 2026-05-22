import {
  LiveKitRoom,
  RoomAudioRenderer,
  ControlBar,
  useVoiceAssistant,
  useLocalParticipant,
  useIsSpeaking,
  useTranscriptions,
  useConnectionState,
  useMediaDeviceSelect,
} from "@livekit/components-react";
import { AgentAudioVisualizerAura } from "@/components/agents-ui/agent-audio-visualizer-aura";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getReport } from "@/api/client";
import { useState, useEffect, useRef } from "react";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Track, ConnectionState } from "livekit-client";

interface InterviewAgentProps {
  token: string;
  sessionId: string;
  onInterviewEnd: (report: any) => void;
}

function MicrophoneSelector() {
  const { devices, activeDeviceId, setActiveMediaDevice } = useMediaDeviceSelect({ kind: 'audioinput', requestPermissions: true });
  const filtered = devices.filter(d => d.deviceId !== '');
  if (filtered.length < 2) return null;
  return (
    <Select value={activeDeviceId} onValueChange={(id) => setActiveMediaDevice(id)}>
      <SelectTrigger className="w-[220px] text-xs">
        <SelectValue placeholder="Select microphone" />
      </SelectTrigger>
      <SelectContent>
        {filtered.map(device => (
          <SelectItem key={device.deviceId} value={device.deviceId} className="text-xs">
            {device.label || `Microphone (${device.deviceId.slice(0, 8)})`}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function InterviewInner({ sessionId, onInterviewEnd }: { sessionId: string; onInterviewEnd: (report: any) => void }) {
  const [isEnding, setIsEnding] = useState(false);
  const [hasEnded, setHasEnded] = useState(false);
  const [hasConnected, setHasConnected] = useState(false);
  
  // Room Connection State
  const roomState = useConnectionState();
  
  // AI Agent Data
  const { state, audioTrack } = useVoiceAssistant();
  
  // Local User Data
  const { localParticipant } = useLocalParticipant();
  const isUserSpeaking = useIsSpeaking(localParticipant);
  const userAudioTrack = localParticipant?.getTrackPublication(Track.Source.Microphone);
  
  // Derived state for the user's Aura visualizer
  const userState = isUserSpeaking ? 'speaking' : 'listening';

  // Try useTranscriptions instead of useChat
  const transcriptions = useTranscriptions();
  
  // Map transcriptions to a unified message format
  // The agent publishes transcriptions for both itself and the user.
  // We differentiate by checking if the transcribed track matches the user's mic track.
  const localMicTrackSid = localParticipant?.getTrackPublication(Track.Source.Microphone)?.trackSid;
  const rawMessages = transcriptions.map((t: any, idx: number) => {
    const transcribedTrackId = t.streamInfo?.attributes?.['lk.transcribed_track_id'];
    const isLocal = transcribedTrackId === localMicTrackSid;
    return {
      id: t.streamInfo?.id || `msg-${idx}`,
      message: t.text || '',
      isLocal,
    };
  }).filter(msg => msg.message);

  // Merge consecutive messages from the same speaker
  const transcriptMessages = rawMessages.reduce<typeof rawMessages>((acc, msg) => {
    const last = acc[acc.length - 1];
    if (last && last.isLocal === msg.isLocal) {
      last.message += ' ' + msg.message;
    } else {
      acc.push({ ...msg });
    }
    return acc;
  }, []);

  // Auto-scroll transcript
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcriptMessages.length]);

  // Track if we ever successfully connected
  useEffect(() => {
    if (roomState === ConnectionState.Connected) {
      setHasConnected(true);
    }
  }, [roomState]);

  // Handle Disconnect ONLY if we were previously connected
  useEffect(() => {
    if (hasConnected && roomState === ConnectionState.Disconnected && !hasEnded) {
      setHasEnded(true); // Ensure this effect only runs once
      setIsEnding(true);
      
      const fetchReportWithRetry = async () => {
        let retries = 10;
        while (retries > 0) {
          try {
            await new Promise(resolve => setTimeout(resolve, 3000));
            const report = await getReport(sessionId);
            onInterviewEnd(report);
            return;
          } catch (error) {
            console.error(`Failed to fetch report. Retries left: ${retries - 1}`);
            retries--;
          }
        }
        
        // If we exhausted retries
        setIsEnding(false);
        alert("The interview ended before a final report could be generated.");
      };
      
      fetchReportWithRetry();
    }
  }, [roomState, hasConnected, sessionId, onInterviewEnd, hasEnded]);

  return (
    <div className="flex flex-col md:flex-row p-4 gap-4 h-full bg-background text-foreground">
      
      {/* Left Side: Visualizers and Controls */}
      <div className="flex-1 flex flex-col items-center justify-center space-y-12 bg-card rounded-lg border shadow-sm p-8 relative">
        <h2 className="text-2xl font-bold absolute top-8 text-center w-full text-primary">
          {state === 'connecting' || state === 'initializing' ? 'Connecting to AI...' : 
           state === 'listening' ? 'AI is Listening...' : 
           state === 'thinking' ? 'AI is Thinking...' :
           state === 'speaking' ? 'AI is Speaking...' : 
           'Interview Room'}
        </h2>

        {/* Dual High-Fidelity Aura Visualizers */}
        <div className="flex flex-col md:flex-row items-center justify-center gap-12 md:gap-24 w-full mt-12">
          
          {/* User Visualizer */}
          <div className="flex flex-col items-center">
            <div className="w-32 h-32 flex items-center justify-center relative scale-125 z-0 pointer-events-none mb-6">
               <AgentAudioVisualizerAura state={userState as any} audioTrack={userAudioTrack as any} />
            </div>
            <span className="text-sm font-bold uppercase tracking-wider text-muted-foreground">You</span>
          </div>

          {/* AI Visualizer */}
          <div className="flex flex-col items-center">
            <div className="w-32 h-32 flex items-center justify-center relative scale-125 z-0 pointer-events-none mb-6">
               <AgentAudioVisualizerAura state={state} audioTrack={audioTrack} />
            </div>
            <span className="text-sm font-bold uppercase tracking-wider text-primary">AI Interviewer</span>
          </div>

        </div>
        
        {/* Standard Controls */}
        <div className="mt-12 z-50 flex flex-col items-center gap-3">
          <MicrophoneSelector />
          <div className="bg-background p-2 rounded-full shadow-lg border">
            <ControlBar controls={{ microphone: true, camera: false, screenShare: false, leave: true }} />
          </div>
        </div>

        {isEnding && (
          <div className="absolute inset-0 bg-background/80 flex items-center justify-center backdrop-blur-sm rounded-lg z-50">
            <div className="text-center space-y-4">
              <div className="text-2xl font-bold animate-pulse text-primary">Generating Report...</div>
              <p className="text-muted-foreground">The interview has ended. Please wait while we process the results.</p>
            </div>
          </div>
        )}
      </div>

      {/* Right Side: Transcript */}
      <div className="w-full md:w-96 flex flex-col bg-card rounded-lg border shadow-sm h-full">
        <CardHeader className="border-b bg-muted/30 pb-4">
          <CardTitle className="text-sm font-medium">Live Transcript</CardTitle>
        </CardHeader>
        <CardContent className="flex-1 overflow-y-auto p-4 flex flex-col">
           {/* Manually render messages to avoid context crashes */}
           <div className="space-y-4 flex flex-col flex-1 justify-end">
             {transcriptMessages.length === 0 && (
               <p className="text-xs text-muted-foreground text-center italic mt-auto">Waiting for conversation to start...</p>
             )}
             {transcriptMessages.map((msg, i) => (
               <div key={i} className={`flex flex-col ${msg.isLocal ? 'items-end' : 'items-start'}`}>
                 <span className="text-[10px] font-bold uppercase text-muted-foreground mb-1">
                   {msg.isLocal ? 'You' : 'AI Interviewer'}
                 </span>
                 <div className={`rounded-2xl px-4 py-2 text-sm max-w-[90%] shadow-sm ${
                   msg.isLocal ? 'bg-primary text-primary-foreground' : 'bg-muted border'
                 }`}>
                   {msg.message}
                 </div>
               </div>
             ))}
             <div ref={transcriptEndRef} />
           </div>
        </CardContent>
      </div>
      
      {/* CRUCIAL: This plays the audio from the room */}
      <RoomAudioRenderer />
    </div>
  );
}

export function InterviewAgent({ token, sessionId, onInterviewEnd }: InterviewAgentProps) {
  const serverUrl = import.meta.env.VITE_LIVEKIT_URL;

  if (!serverUrl) {
    return <div className="p-8 text-center text-destructive">VITE_LIVEKIT_URL is missing in .env</div>;
  }

  return (
    <LiveKitRoom
      serverUrl={serverUrl}
      token={token}
      connect={true}
      audio={true}
      video={false}
      onError={(err) => console.error("LiveKit Room Error:", err)}
      className="h-full w-full"
    >
      <InterviewInner sessionId={sessionId} onInterviewEnd={onInterviewEnd} />
    </LiveKitRoom>
  );
}
