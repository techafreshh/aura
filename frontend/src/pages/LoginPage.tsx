import { type FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import {
  apiErrorMessage,
  loginWithPassword,
  registerUser,
  resendVerification,
} from '@/api/client';
import { AuthShell, OAuthButtons } from '@/components/auth/AuthShell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

type Mode = 'signin' | 'signup';

export function LoginPage() {
  const { setAuth, login } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState<Mode>('signin');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [needsVerification, setNeedsVerification] = useState(false);
  const [resent, setResent] = useState(false);

  const onSuccess = (token: string, user: { id: string; email: string; name: string; role: 'admin' | 'candidate' | 'recruiter' | ''; avatar_url?: string | null }) => {
    setAuth(token, { ...user, avatar_url: user.avatar_url ?? undefined });
    // Same routing as the OAuth callback: deep links survive the round-trip,
    // and users who have not chosen a role go through the picker first.
    const returnTo = sessionStorage.getItem('aura_return_to');
    sessionStorage.removeItem('aura_return_to');
    if (returnTo) {
      navigate(returnTo, { replace: true });
    } else if (user.role === 'admin') {
      navigate('/admin', { replace: true });
    } else if (user.role === 'recruiter') {
      navigate('/recruiter', { replace: true });
    } else if (user.role === '') {
      navigate('/choose-role', { replace: true });
    } else {
      navigate('/interview', { replace: true });
    }
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setNotice('');
    setNeedsVerification(false);
    setResent(false);
    setBusy(true);
    try {
      if (mode === 'signup') {
        const { message } = await registerUser(email, password, name);
        setNotice(message);
        setMode('signin');
      } else {
        const { token, user } = await loginWithPassword(email, password);
        onSuccess(token, user);
      }
    } catch (err) {
      const msg = apiErrorMessage(err);
      setError(msg);
      const status = (err as { response?: { status?: number } }).response?.status;
      const code = (err as { response?: { data?: { detail?: { code?: string } } } }).response?.data?.detail?.code;
      if (status === 403 && code === 'email_not_verified') {
        setNeedsVerification(true);
      }
    } finally {
      setBusy(false);
    }
  };

  const onResend = async () => {
    setError('');
    setBusy(true);
    try {
      const { message } = await resendVerification(email);
      setResent(true);
      setNotice(message);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      title={mode === 'signin' ? 'Sign in to Aura' : 'Create your account'}
      subtitle={
        mode === 'signin'
          ? 'Practice a real-time AI voice interview.'
          : 'Start with a free AI voice interview.'
      }
      footer={
        mode === 'signin' ? (
          <span>
            New to Aura?{' '}
            <button
              type="button"
              className="font-medium text-primary underline-offset-4 hover:underline"
              onClick={() => {
                setMode('signup');
                setError('');
                setNotice('');
              }}
            >
              Create an account
            </button>
          </span>
        ) : (
          <span>
            Already have an account?{' '}
            <button
              type="button"
              className="font-medium text-primary underline-offset-4 hover:underline"
              onClick={() => {
                setMode('signin');
                setError('');
                setNotice('');
              }}
            >
              Sign in
            </button>
          </span>
        )
      }
    >
      <OAuthButtons onProvider={(p) => login(p)} />

      <div className="my-5 flex items-center gap-3 text-xs uppercase tracking-wider text-muted-foreground">
        <span className="h-px flex-1 bg-border" />or<span className="h-px flex-1 bg-border" />
      </div>

      {needsVerification && (
        <div className="mb-4 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
          <p>{error}</p>
          {!resent ? (
            <button
              type="button"
              onClick={onResend}
              disabled={busy}
              className="mt-2 font-medium text-amber-100 underline underline-offset-4 disabled:opacity-50"
            >
              Resend verification email
            </button>
          ) : (
            <p className="mt-2 text-amber-100/80">Verification email sent — check your inbox.</p>
          )}
        </div>
      )}
      {!needsVerification && error && (
        <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-red-300">
          {error}
        </div>
      )}
      {notice && !error && (
        <div className="mb-4 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">
          {notice}
        </div>
      )}

      <form onSubmit={onSubmit} className="grid gap-3">
        {mode === 'signup' && (
          <label className="grid gap-1.5">
            <span className="text-sm text-muted-foreground">Name</span>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ada Lovelace" maxLength={100} />
          </label>
        )}
        <label className="grid gap-1.5">
          <span className="text-sm text-muted-foreground">Email</span>
          <Input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
          />
        </label>
        <label className="grid gap-1.5">
          <span className="text-sm text-muted-foreground">Password</span>
          <Input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={mode === 'signup' ? 'At least 8 characters' : 'Your password'}
            autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
          />
        </label>
        {mode === 'signin' && (
          <div className="text-right">
            <Link to="/forgot-password" className="text-xs text-muted-foreground underline-offset-4 hover:underline">
              Forgot password?
            </Link>
          </div>
        )}
        <Button type="submit" disabled={busy} className="mt-1 w-full">
          {busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : 'Create account'}
        </Button>
      </form>
    </AuthShell>
  );
}
