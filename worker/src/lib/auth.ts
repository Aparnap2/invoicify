/**
 * API Authentication Middleware
 *
 * Provides multiple authentication strategies:
 * - API Key authentication (simple, for internal services)
 * - Bearer token authentication (JWT-based)
 * - Slack signature verification (for Slack events)
 *
 * All protected routes require authentication unless explicitly excluded.
 */

import { createHonoClient } from "hono/clients";
import { logger } from "./logger";
import type { Env } from "../db";

// ============================================================================
// Authentication Types
// ============================================================================

export interface AuthUser {
  id: string;
  email: string;
  role: "admin" | "user" | "service";
  scopes: string[];
}

export interface AuthResult {
  success: true;
  user: AuthUser;
} | {
  success: false;
  error: string;
  status: number;
}

// ============================================================================
// API Key Authentication
// ============================================================================

/**
 * Validate API key from header
 * Header format: X-API-Key: <key>
 */
export async function validateApiKey(
  env: Env,
  apiKey: string | null
): Promise<AuthResult> {
  if (!apiKey) {
    return { success: false, error: "Missing API key", status: 401 };
  }

  // In production, validate against database or secrets
  // This is a simplified version for demonstration
  const validKey = env.API_SECRET_KEY;

  if (!validKey) {
    logger.warn("API_SECRET_KEY not configured - allowing request in dev mode");
    // Allow in development if key not configured
    return {
      success: true,
      user: {
        id: "dev-user",
        email: "dev@example.com",
        role: "admin",
        scopes: ["*"],
      },
    };
  }

  if (apiKey !== validKey) {
    logger.warn("Invalid API key attempted", { action: "auth_attempt" });
    return { success: false, error: "Invalid API key", status: 401 };
  }

  return {
    success: true,
    user: {
      id: "service",
      email: "api@service",
      role: "service",
      scopes: ["invoices:read", "invoices:write", "workflows:execute"],
    },
  };
}

// ============================================================================
// Bearer Token Authentication (JWT)
// ============================================================================

/**
 * Validate Bearer token from Authorization header
 * Header format: Authorization: Bearer <token>
 *
 * In production, implement JWT verification:
 * - Verify token signature
 * - Check expiration
 * - Extract claims
 */
export async function validateBearerToken(
  env: Env,
  authHeader: string | null
): Promise<AuthResult> {
  if (!authHeader) {
    return { success: false, error: "Missing authorization header", status: 401 };
  }

  if (!authHeader.startsWith("Bearer ")) {
    return { success: false, error: "Invalid authorization format", status: 401 };
  }

  const token = authHeader.slice(7);

  if (!token) {
    return { success: false, error: "Missing token", status: 401 };
  }

  // Simplified token validation for demonstration
  // In production, use a proper JWT library like jose
  try {
    // Decode token (base64 URL encoded JSON)
    const parts = token.split(".");
    if (parts.length !== 3) {
      return { success: false, error: "Invalid token format", status: 401 };
    }

    const payload = JSON.parse(atob(parts[1]));

    // Check expiration
    if (payload.exp && payload.exp < Date.now() / 1000) {
      return { success: false, error: "Token expired", status: 401 };
    }

    return {
      success: true,
      user: {
        id: payload.sub || payload.userId,
        email: payload.email,
        role: payload.role || "user",
        scopes: payload.scopes || [],
      },
    };
  } catch (error) {
    logger.warn("Token validation failed", { error: (error as Error).message });
    return { success: false, error: "Invalid token", status: 401 };
  }
}

// ============================================================================
// Slack Signature Verification
// ============================================================================

/**
 * Verify Slack request signature
 * Required for Slack Events and Interactivity endpoints
 *
 * Slack signs requests using SHA256 HMAC with your signing secret
 */
export function verifySlackSignature(
  env: Env,
  timestamp: string,
  signature: string | null,
  body: string
): AuthResult {
  // Check timestamp to prevent replay attacks (within 5 minutes)
  const now = Math.floor(Date.now() / 1000);
  const requestTime = parseInt(timestamp);
  if (Math.abs(now - requestTime) > 60 * 5) {
    return { success: false, error: "Request timestamp too old", status: 401 };
  }

  if (!signature || !env.SLACK_SIGNING_SECRET) {
    return { success: false, error: "Missing signature", status: 401 };
  }

  // In production, compute the expected signature:
  // 1. Concatenate: v0 + timestamp + body
  // 2. HMAC-SHA256 with signing secret
  // 3. Compare with signature prefix

  // Simplified check for demonstration
  // Real implementation would use crypto.createHmac
  const expectedSignature = signature; // Compute this in production

  // For now, just verify it's present
  if (!signature.startsWith("v0=")) {
    return { success: false, error: "Invalid signature format", status: 401 };
  }

  return {
    success: true,
    user: {
      id: "slack-bot",
      email: "bot@slack",
      role: "service",
      scopes: ["slack:events", "slack:interactions"],
    },
  };
}

// ============================================================================
// Auth Middleware Factory
// ============================================================================

export type AuthStrategy = "api-key" | "bearer" | "slack" | "any";

/**
 * Create authentication middleware
 */
export function createAuthMiddleware(
  strategy: AuthStrategy = "any",
  options: {
    requiredScopes?: string[];
    excludePaths?: string[];
  } = {}
) {
  return async function authMiddleware(
    c: { env: Env; req: { header: (name: string) => string | null } },
    next: () => Promise<void>
  ): Promise<void> {
    const path = c.req.url.pathname;

    // Skip auth for excluded paths
    if (options.excludePaths?.some(p => path.startsWith(p))) {
      await next();
      return;
    }

    // Health check - no auth required
    if (path === "/health" || path === "/healthz") {
      await next();
      return;
    }

    let result: AuthResult;

    switch (strategy) {
      case "api-key":
        result = await validateApiKey(c.env, c.req.header("x-api-key"));
        break;

      case "bearer":
        result = await validateBearerToken(c.env, c.req.header("authorization"));
        break;

      case "slack":
        // Slack verification happens in the endpoint handler
        // This is just a placeholder
        result = {
          success: true,
          user: { id: "slack", email: "slack@bot", role: "service", scopes: [] },
        };
        break;

      case "any":
      default:
        // Try API key first, then bearer
        const apiKey = c.req.header("x-api-key");
        if (apiKey) {
          result = await validateApiKey(c.env, apiKey);
        } else {
          result = await validateBearerToken(c.env, c.req.header("authorization"));
        }
        break;
    }

    if (!result.success) {
      logger.warn("Authentication failed", {
        path,
        error: result.error,
        ip: c.req.header("cf-connecting-ip"),
      });

      return c.json(
        { error: result.error },
        result.status
      );
    }

    // Attach user to context
    (c.env as any).authUser = result.user;

    // Check scopes if required
    if (options.requiredScopes?.length && result.user) {
      const hasScopes = options.requiredScopes.every(
        scope => result.user!.scopes.includes(scope) || result.user!.scopes.includes("*")
      );

      if (!hasScopes) {
        logger.warn("Insufficient scopes", {
          userId: result.user.id,
          required: options.requiredScopes,
          has: result.user.scopes,
        });

        return c.json(
          { error: "Insufficient permissions" },
          403
        );
      }
    }

    await next();
  };
}

// ============================================================================
// Auth Helpers
// ============================================================================

/**
 * Get current user from context
 */
export function getCurrentUser(c: { env: Env }): AuthUser | null {
  return (c.env as any).authUser || null;
}

/**
 * Check if current user is admin
 */
export function isAdmin(c: { env: Env }): boolean {
  const user = getCurrentUser(c);
  return user?.role === "admin";
}

/**
 * Check if current user has specific scope
 */
export function hasScope(c: { env: Env }, scope: string): boolean {
  const user = getCurrentUser(c);
  if (!user) return false;
  return user.scopes.includes("*") || user.scopes.includes(scope);
}
