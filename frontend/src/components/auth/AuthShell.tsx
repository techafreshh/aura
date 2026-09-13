import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { AuraMark } from '@/components/ui/aura-brand';

/**
 * Shared dark shell for the auth pages (login, verify, forgot/reset password),
 * matching the landing page's indigo-on-near-black look without pulling in
 * the full landing CSS.
 */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 py-12">
      <Link to="/" className="mb-8 flex items-center gap-2 text-foreground" aria-label="Aura home">
        <AuraMark size={26} />
        <span className="text-lg font-semibold tracking-tight">Aura</span>
      </Link>
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-8 shadow-lg">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </div>
      {footer && <div className="mt-6 text-sm text-muted-foreground">{footer}</div>}
    </div>
  );
}

export function OAuthButtons({ onProvider }: { onProvider: (p: 'google' | 'github') => void }) {
  return (
    <div className="grid gap-2">
      <button
        type="button"
        onClick={() => onProvider('google')}
        className="flex h-9 w-full items-center justify-center gap-2 rounded-md border border-input bg-transparent text-sm font-medium text-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
      >
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <path fill="#4285F4" d="M15.68 8.18c0-.57-.05-1.12-.15-1.65H8v3.12h4.3a3.68 3.68 0 0 1-1.6 2.42v2h2.59c1.51-1.4 2.39-3.45 2.39-5.89Z" />
          <path fill="#34A853" d="M8 16c2.17 0 3.99-.72 5.32-1.95l-2.6-2c-.72.48-1.64.77-2.72.77-2.09 0-3.87-1.41-4.5-3.31H.79v2.07A8 8 0 0 0 8 16Z" />
          <path fill="#FBBC05" d="M3.5 9.51a4.8 4.8 0 0 1 0-3.02V4.42H.79a8 8 0 0 0 0 7.16l2.71-2.07Z" />
          <path fill="#EA4335" d="M8 3.18c1.18 0 2.23.4 3.06 1.2l2.3-2.3A8 8 0 0 0 .79 4.42l2.71 2.07C4.13 4.6 5.91 3.18 8 3.18Z" />
        </svg>
        Continue with Google
      </button>
      <button
        type="button"
        onClick={() => onProvider('github')}
        className="flex h-9 w-full items-center justify-center gap-2 rounded-md border border-input bg-transparent text-sm font-medium text-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
      >
        <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" clipRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
        </svg>
        Continue with GitHub
      </button>
    </div>
  );
}
