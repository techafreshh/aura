import { type FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiErrorMessage, requestPasswordReset } from '@/api/client';
import { AuthShell } from '@/components/auth/AuthShell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await requestPasswordReset(email);
      setSent(true);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      title="Forgot your password?"
      subtitle="Enter your email and we'll send you a reset link."
      footer={
        <span>
          Remembered it?{' '}
          <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
            Back to sign in
          </Link>
        </span>
      }
    >
      {sent ? (
        <p className="text-sm text-emerald-300">
          If an account with that email exists, a reset link is on its way. Check your inbox — the link
          expires in one hour.
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
            <Button type="submit" disabled={busy} className="mt-1 w-full">
              {busy ? 'Sending…' : 'Send reset link'}
            </Button>
          </form>
        </>
      )}
    </AuthShell>
  );
}
