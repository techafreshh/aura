import { Link, useSearchParams } from 'react-router-dom';
import { AuthShell } from '@/components/auth/AuthShell';
import { Button } from '@/components/ui/button';

const STATES = {
  success: {
    title: 'Email verified',
    body: 'Your email address is confirmed. You can now sign in and start your first interview.',
    tone: 'text-emerald-300',
  },
  expired: {
    title: 'Link expired',
    body: 'This verification link has expired. Sign in and request a new verification email.',
    tone: 'text-amber-300',
  },
  invalid: {
    title: 'Invalid link',
    body: "We couldn't verify your email with this link. It may have already been used, or the account may no longer need verification.",
    tone: 'text-red-300',
  },
} as const;

export function EmailVerified() {
  const [params] = useSearchParams();
  const status = params.get('status');
  const state = STATES[(status as keyof typeof STATES) ?? 'invalid'] ?? STATES.invalid;

  return (
    <AuthShell title={state.title} subtitle={undefined} footer={undefined}>
      <p className={`text-sm ${state.tone}`}>{state.body}</p>
      <Button asChild className="mt-6 w-full">
        <Link to="/login">Go to sign in</Link>
      </Button>
    </AuthShell>
  );
}
