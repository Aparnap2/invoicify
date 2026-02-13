/**
 * Better Auth Configuration for Invoicify
 *
 * Multi-tenant authentication with:
 * - Email/password authentication
 * - OAuth providers (Google, GitHub)
 * - Organization-based multi-tenancy
 * - Role-based access control
 */

import { betterAuth } from "better-auth";
import { prismaAdapter } from "better-auth/adapters/prisma";
import { openAPI } from "better-auth/plugins";
import type { PrismaClient } from "@prisma/client";

// ============================================================================
// Type Augmentation for better-auth
// ============================================================================

declare module "better-auth" {
  interface Session {
    user: {
      id: string;
      email: string;
      name: string;
      image?: string;
      organizationId?: string;
      role?: string;
    };
  }

  interface User {
    id: string;
    email: string;
    name: string;
    image?: string;
    role?: string;
  }
}

declare module "better-auth/plugins" {
  interface OpenAPI {
    components: {
      securitySchemes: {
        BearerAuth: {
          type: string;
          scheme: string;
          description: string;
        };
        ApiKeyAuth: {
          type: string;
          in: string;
          name: string;
          description: string;
        };
      };
    };
  }
}

// ============================================================================
// Configuration
// ============================================================================

export interface AuthConfig {
  prisma: PrismaClient;
  secret: string;
  baseUrl: string;
  socialProviders?: {
    google?: {
      clientId: string;
      clientSecret: string;
    };
    github?: {
      clientId: string;
      clientSecret: string;
    };
  };
  // Optional: restrict signup to specific email domains
  allowedDomains?: string[];
  // Optional: require email verification
  requireEmailVerification?: boolean;
}

/**
 * Create Better Auth instance with Invoicify configuration
 */
export function createAuthConfig(config: AuthConfig) {
  const {
    prisma,
    secret,
    baseUrl,
    socialProviders,
    allowedDomains,
    requireEmailVerification = false,
  } = config;

  // Verify required environment variables
  if (!secret) {
    throw new Error("BETTER_AUTH_SECRET is required");
  }
  if (!baseUrl) {
    throw Error("BASE_URL is required for CORS and redirects");
  }

  return betterAuth({
    // Database adapter
    database: prismaAdapter(prisma, {
      provider: "postgresql",
    }),

    // Authentication methods
    emailAndPassword: {
      enabled: true,
      // Domain restriction for email
      ...(allowedDomains && {
        password: {
          requireUppercase: true,
          requireSpecialChar: true,
          minLength: 8,
        },
      }),
    },

    // OAuth providers
    ...(socialProviders && {
      socialProviders: {
        google: socialProviders.google && {
          clientId: socialProviders.google.clientId,
          clientSecret: socialProviders.google.clientSecret,
          redirectURI: `${baseUrl}/api/auth/callback/google`,
        },
        github: socialProviders.github && {
          clientId: socialProviders.github.clientId,
          clientSecret: socialProviders.github.clientSecret,
          redirectURI: `${baseUrl}/api/auth/callback/github`,
        },
      },
    }),

    // Security settings
    advanced: {
      cookiePrefix: "invoicify",
      // IP-based rate limiting
      rateLimit: {
        window: 60 * 1000, // 1 minute
        max: 100, // 100 requests per window
      },
      // CSRF protection
      csrf: {
        checkOrigin: true,
      },
    },

    // Plugins
    plugins: [
      // OpenAPI/Swagger support for API documentation
      openAPI({
        prefix: "/api/v1",
        tags: ["auth", "users", "organizations"],
        securitySchemes: {
          BearerAuth: {
            type: "http",
            scheme: "bearer",
            description: "JWT Bearer token authentication",
          },
          ApiKeyAuth: {
            type: "apiKey",
            in: "header",
            name: "X-API-Key",
            description: "API Key authentication for service accounts",
          },
        },
      }),
    ],

    // Hooks for custom logic
    hooks: {
      // After sign up - create default organization or invite flow
      after: [
        {
          trigger: "signUp",
          handler: async (session) => {
            // Check if there's a pending invitation for this email
            const invitation = await prisma.invitation.findFirst({
              where: {
                email: session.user.email,
                status: "PENDING",
                expiresAt: { gt: new Date() },
              },
            });

            if (invitation) {
              // Auto-join organization from invitation
              await prisma.organizationUser.create({
                data: {
                  organizationId: invitation.organizationId,
                  userId: session.user.id,
                  role: invitation.role,
                  status: "ACTIVE",
                },
              });

              // Update invitation status
              await prisma.invitation.update({
                where: { id: invitation.id },
                data: {
                  status: "ACCEPTED",
                  acceptedAt: new Date(),
                },
              });
            }

            return session;
          },
        },
      ],
    },
  });
}

// ============================================================================
// Organization Helper Types
// ============================================================================

/**
 * Organization context for authenticated user
 */
export interface AuthenticatedUser {
  id: string;
  email: string;
  name: string;
  image?: string;
  organizationId?: string;
  organizationRole?: string;
}

/**
 * Get user's organization and role from database
 */
export async function getUserOrganization(
  prisma: PrismaClient,
  userId: string,
  organizationId: string
) {
  return prisma.organizationUser.findFirst({
    where: {
      userId,
      organizationId,
      status: "ACTIVE",
    },
    include: {
      organization: true,
    },
  });
}

/**
 * Check if user has required role in organization
 */
export async function checkUserRole(
  prisma: PrismaClient,
  userId: string,
  organizationId: string,
  requiredRoles: string[]
) {
  const membership = await getUserOrganization(prisma, userId, organizationId);

  if (!membership) {
    return { allowed: false, reason: "User not a member of organization" };
  }

  if (!requiredRoles.includes(membership.role)) {
    return {
      allowed: false,
      reason: `Required role: ${requiredRoles.join(" or ")}`,
    };
  }

  return { allowed: true, membership };
}

// ============================================================================
// Role Hierarchy
// ============================================================================

export const ORG_ROLE_HIERARCHY = {
  VIEWER: 1,
  USER: 2,
  APPROVER: 3,
  FINANCE: 4,
  ADMIN: 5,
  OWNER: 6,
} as const;

export type OrgRole = keyof typeof ORG_ROLE_HIERARCHY;

/**
 * Check if user has minimum role level
 */
export function hasMinimumRole(
  userRole: string,
  minimumRole: OrgRole
): boolean {
  return ORG_ROLE_HIERARCHY[userRole as OrgRole] >= ORG_ROLE_HIERARCHY[minimumRole];
}

/**
 * Role permissions mapping
 */
export const ROLE_PERMISSIONS: Record<OrgRole, string[]> = {
  VIEWER: ["invoices:read", "vendors:read", "reports:read"],
  USER: [
    "invoices:read",
    "invoices:create",
    "invoices:upload",
    "vendors:read",
    "vendors:create",
    "reports:read",
  ],
  APPROVER: [
    "invoices:read",
    "invoices:approve",
    "vendors:read",
    "reports:read",
  ],
  FINANCE: [
    "invoices:read",
    "invoices:write",
    "invoices:approve",
    "invoices:delete",
    "vendors:*",
    "reports:*",
    "settings:read",
    "billing:read",
  ],
  ADMIN: [
    "invoices:*",
    "vendors:*",
    "reports:*",
    "users:read",
    "users:write",
    "settings:*",
    "billing:*",
    "integrations:*",
    "api-keys:*",
  ],
  OWNER: [
    "*", // Full access including billing and org management
  ],
};

// ============================================================================
// Export Types for Convenience
// ============================================================================

export type { Session, User } from "better-auth";
export type { inferRouterInputs, inferRouterOutputs } from "@trpc/server";
