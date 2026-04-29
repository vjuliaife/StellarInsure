"use client";

import React, { ErrorInfo, ReactNode, useCallback, useState } from "react";
import { Icon } from "./icon";
import { logError } from "@/lib/error-logger";

// ── Types ──────────────────────────────────────────────────────────────────

export type ApiErrorVariant = "section" | "card" | "inline";

interface ApiErrorBoundaryProps {
  children: ReactNode;
  /**
   * Display variant:
   * - `section`  Full-width section replacement (default)
   * - `card`     Contained card-sized fallback
   * - `inline`   Single-line inline error for small components
   */
  variant?: ApiErrorVariant;
  /** Optional section label for screen readers. */
  label?: string;
  /** Custom fallback rendered instead of the default error UI. */
  fallback?: (error: Error, retry: () => void) => ReactNode;
}

interface BoundaryState {
  hasError: boolean;
  error: Error | null;
}

// ── Class boundary ─────────────────────────────────────────────────────────

class ApiErrorBoundaryInner extends React.Component<
  ApiErrorBoundaryProps & { onError?: (e: Error, info: ErrorInfo) => void },
  BoundaryState
> {
  constructor(props: ApiErrorBoundaryProps & { onError?: (e: Error, info: ErrorInfo) => void }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    logError(error, {
      componentStack: errorInfo.componentStack,
      tags: { component: "ApiErrorBoundary" }
    });
    this.props.onError?.(error, errorInfo);
  }

  retry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (!this.state.hasError || !this.state.error) {
      return this.props.children;
    }

    if (this.props.fallback) {
      return <>{this.props.fallback(this.state.error, this.retry)}</>;
    }

    return (
      <ApiErrorFallback
        error={this.state.error}
        variant={this.props.variant ?? "section"}
        label={this.props.label}
        onRetry={this.retry}
      />
    );
  }
}

// ── Fallback UI ────────────────────────────────────────────────────────────

interface FallbackProps {
  error: Error;
  variant: ApiErrorVariant;
  label?: string;
  onRetry: () => void;
}

function ApiErrorFallback({ error, variant, label, onRetry }: FallbackProps) {
  const isApiError = isNetworkOrApiError(error);
  const message = isApiError
    ? "We couldn't load this content. Check your connection and try again."
    : "Something went wrong in this section.";

  if (variant === "inline") {
    return (
      <span
        role="alert"
        aria-label={label}
        className="api-error-boundary api-error-boundary--inline"
      >
        <Icon name="alert" size="sm" tone="danger" aria-hidden="true" />
        <span className="api-error-boundary__inline-msg">{message}</span>
        <button
          type="button"
          className="api-error-boundary__retry-link"
          onClick={onRetry}
          aria-label="Retry loading this section"
        >
          Retry
        </button>
      </span>
    );
  }

  if (variant === "card") {
    return (
      <div
        role="alert"
        aria-label={label ?? "Section error"}
        className="api-error-boundary api-error-boundary--card"
      >
        <Icon name="alert" size="md" tone="danger" aria-hidden="true" />
        <p className="api-error-boundary__message">{message}</p>
        <button
          type="button"
          className="api-error-boundary__retry-btn"
          onClick={onRetry}
        >
          Try again
        </button>
      </div>
    );
  }

  // Default: section
  return (
    <section
      role="alert"
      aria-label={label ?? "Section error"}
      className="api-error-boundary api-error-boundary--section"
    >
      <div className="api-error-boundary__inner">
        <Icon name="alert" size="lg" tone="danger" aria-hidden="true" />
        <h2 className="api-error-boundary__heading">Unable to load content</h2>
        <p className="api-error-boundary__message">{message}</p>
        {process.env.NODE_ENV !== "production" && (
          <details className="api-error-boundary__details">
            <summary>Error details</summary>
            <pre>{error.message}</pre>
          </details>
        )}
        <button
          type="button"
          className="api-error-boundary__retry-btn"
          onClick={onRetry}
        >
          Try again
        </button>
      </div>
    </section>
  );
}

// ── Public component ───────────────────────────────────────────────────────

/**
 * Scoped error boundary for page sections and async components.
 *
 * Unlike the root `ErrorBoundary` (which covers the full page), this component
 * isolates failures to a specific section, keeping the rest of the UI functional.
 *
 * @example
 * <ApiErrorBoundary variant="card" label="Policy list">
 *   <PolicyList />
 * </ApiErrorBoundary>
 */
export function ApiErrorBoundary({
  children,
  variant = "section",
  label,
  fallback,
}: ApiErrorBoundaryProps) {
  const [errorCount, setErrorCount] = useState(0);

  const handleError = useCallback(() => {
    setErrorCount((n) => n + 1);
  }, []);

  return (
    <ApiErrorBoundaryInner
      key={errorCount}
      variant={variant}
      label={label}
      fallback={fallback}
      onError={handleError}
    >
      {children}
    </ApiErrorBoundaryInner>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────

function isNetworkOrApiError(error: Error): boolean {
  const msg = error.message.toLowerCase();
  return (
    msg.includes("fetch") ||
    msg.includes("network") ||
    msg.includes("failed to load") ||
    msg.includes("timeout") ||
    error.name === "TypeError"
  );
}
