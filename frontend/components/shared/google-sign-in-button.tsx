"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

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
      if (!window.google || !buttonRef.current) return;
      window.google.accounts.id.initialize({ client_id: clientId, callback: handleCredentialResponse });
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: "outline",
        size: "large",
        width: 360,
      });
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
    // Fails silently in the UI rather than rendering a broken button — but
    // warn in development so a missing env var isn't a mystery.
    if (process.env.NODE_ENV === "development") {
      console.warn("NEXT_PUBLIC_GOOGLE_CLIENT_ID is not set — Google Sign-In button hidden.");
    }
    return null;
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
