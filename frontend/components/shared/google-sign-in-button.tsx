"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api-client";
import { setAccessToken } from "@/lib/token-store";
import { useAuth } from "@/providers/auth-provider";
import type { LoginResponse, UserRole } from "@/types/auth";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: Record<string, unknown>) => void;
          renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
        };
      };
    };
  }
}

interface GoogleSignInButtonProps {
  /** Only used if this Google sign-in creates a brand-new account. */
  role?: Extract<UserRole, "student" | "tpo">;
}

/**
 * Google only accepts the exact page origin (scheme + host + port) and does not
 * support 127.0.0.1 for local development. Build the hint from the live origin
 * so it stays correct on a different port or host.
 */
function originHelpMessage(): string {
  const { origin, hostname, port } = window.location;
  if (hostname === "127.0.0.1" || hostname === "[::1]") {
    const local = `http://localhost${port ? `:${port}` : ""}`;
    return (
      `Google Sign-In does not work from ${origin}. Open the app at ${local} instead ` +
      `(127.0.0.1 is not an allowed Google origin), and add both http://localhost and ` +
      `${local} to the OAuth client's Authorized JavaScript origins in Google Cloud Console.`
    );
  }
  return (
    `Google Sign-In is blocked for ${origin}. Add ${origin} (and http://localhost) to the ` +
    `OAuth client's Authorized JavaScript origins in Google Cloud Console, then refresh this page.`
  );
}

/**
 * Renders Google's own "Sign in with Google" button. On success, sends the
 * ID token to POST /auth/google, which either logs in an existing account
 * or creates a new one — same response shape as the password login flow,
 * so the redirect logic below matches app/(auth)/login/page.tsx exactly.
 */
export function GoogleSignInButton({ role = "student" }: GoogleSignInButtonProps) {
  const buttonRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const { setUser } = useAuth();
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!clientId) return;

    async function handleCredentialResponse(googleResponse: { credential: string }) {
      setError(null);
      try {
        const { data } = await apiClient.post<LoginResponse>("/auth/google", {
          credential: googleResponse.credential,
          role,
        });
        setAccessToken(data.access_token);
        setUser(data.user);
        document.cookie = `placer_role=${data.user.role}; path=/; SameSite=Strict`;

        const roleHome =
          data.user.role === "admin" ? "/admin/dashboard" : data.user.role === "tpo" ? "/tpo/dashboard" : "/dashboard";
        router.push(data.profile_incomplete ? `${roleHome}?complete_profile=true` : roleHome);
      } catch (err: any) {
        // Previously swallowed silently, which made a failed Google sign-in
        // look like "nothing happened". Surface the backend's reason instead.
        const detail = err?.response?.data?.detail;
        if (typeof detail === "string") {
          setError(detail);
        } else if (err?.response) {
          setError("Google sign-in failed. Please try again.");
        } else {
          setError("Couldn't reach the server. Check that the backend is running and try again.");
        }
      }
    }

    function initialize() {
      if (!window.google?.accounts?.id || !buttonRef.current) {
        setError("Google Sign-In failed to load. Check your connection and refresh the page.");
        return;
      }

      // Google Identity Services does not support 127.0.0.1 as a local origin,
      // even when it is registered. Surface that instead of rendering a button
      // that can never complete sign-in.
      const host = window.location.hostname;
      if (host === "127.0.0.1" || host === "[::1]") {
        setError(originHelpMessage());
        return;
      }

      try {
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: handleCredentialResponse,
          ux_mode: "popup",
          auto_select: false,
        });

        // StrictMode runs effects twice in development; clear the container so
        // the second initialize() doesn't append a second Google button.
        buttonRef.current.innerHTML = "";
        window.google.accounts.id.renderButton(buttonRef.current, {
          theme: "outline",
          size: "large",
          width: 360,
        });
      } catch {
        setError(originHelpMessage());
      }
    }

    if (window.google) {
      initialize();
      return;
    }

    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = initialize;
    script.onerror = () => {
      setError("Couldn't load Google Sign-In. Check your connection and refresh the page.");
    };
    document.body.appendChild(script);

    return () => {
      document.body.removeChild(script);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, role]);

  if (!clientId) {
    return (
      <div className="flex w-full flex-col items-center gap-2">
        <Button type="button" variant="outline" className="w-full" disabled>
          Sign in with Google
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          Google Sign-In isn&apos;t configured. Set <code>NEXT_PUBLIC_GOOGLE_CLIENT_ID</code> in{" "}
          <code>frontend/.env.local</code> and restart the frontend.
        </p>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col items-center gap-2">
      <div ref={buttonRef} className="flex justify-center" />
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
