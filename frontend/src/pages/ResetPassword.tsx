import { type FormEvent, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { apiErrorMessage, resetPassword } from '@/api/client';
import { AuthShell } from '@/components/auth/AuthShell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get('token') ?? '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      await resetPassword(token, password);
      setDone(true);
      setTimeout(() => navigate('/login', { replace: true }), 2500);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <AuthShell
        title="Invalid reset link"
        footer={
          <span>
            Need a new one?{' '}
            <Link to="/forgot-password" className="font-medium text-primary underline-offset-4 hover:underline">
              Request a reset link
            </Link>
          </span>
        }
      >
        <p className="text-sm text-red-300">
          This page was opened without a reset token. Request a fresh link from the forgot-password page.
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Choose a new password"
      subtitle="Your new password must be at least 8 characters."
      footer={
        <span>
          <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
            Back to sign in
          </Link>
        </span>
      }
    >
      {done ? (
        <p className="text-sm text-emerald-300">
          Password updated. Redirecting you to sign in…
        </p>
      ) : (
        <>
          {error && (
            <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-red-300">
              {error}
            </div>
          )}
          <form onSubmit={onSubmit} className="grid gap-3">
            <label className="grid gap-1.5">
              <span className="text-sm text-muted-foreground">New password</span>
              <Input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </label>
            <label className="grid gap-1.5">
              <span className="text-sm text-muted-foreground">Confirm new password</span>
              <Input
                type="password"
                required
                minLength={8}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
              />
            </label>
            <Button type="submit" disabled={busy} className="mt-1 w-full">
              {busy ? 'Updating…' : 'Update password'}
            </Button>
          </form>
        </>
      )}
    </AuthShell>
  );
}
