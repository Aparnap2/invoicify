/**
 * Organizations Route Module
 *
 * Multi-tenant organization management endpoints including:
 * - Organization CRUD operations
 * - Member management with role-based access control
 * - Invitation system for team collaboration
 *
 * Requires authentication via Bearer token or API key.
 */

import { Hono } from "hono";
import { getDb, schema } from "../db";
import { eq, and, desc, sql } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import type { Env } from "../db";
import {
  ORG_ROLE_HIERARCHY,
  hasMinimumRole,
  isOwner,
  validateBearerToken,
  validateApiKey,
  type OrgRole,
} from "../lib/auth";

// ============================================================================
// Types & Enums
// ============================================================================

/**
 * Organization role enum matching auth module
 */
export const OrgRole = {
  OWNER: "OWNER",
  ADMIN: "ADMIN",
  FINANCE: "FINANCE",
  APPROVER: "APPROVER",
  USER: "USER",
  VIEWER: "VIEWER",
} as const;

export type OrgRoleType = (typeof OrgRole)[keyof typeof OrgRole];

/**
 * Invitation status enum
 */
export const InviteStatus = {
  PENDING: "PENDING",
  ACCEPTED: "ACCEPTED",
  EXPIRED: "EXPIRED",
  REVOKED: "REVOKED",
} as const;

export type InviteStatusType = (typeof InviteStatus)[keyof typeof InviteStatus];

// Use schema tables from db/schema.ts
const { organizations, organizationUsers, invitations } = schema;

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Generate URL-friendly slug from organization name
 */
function generateSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .substring(0, 63);
}

/**
 * Generate secure invitation token
 */
function generateInvitationToken(): string {
  return uuidv4();
}

/**
 * Calculate invitation expiration date (7 days from now)
 */
function getInvitationExpiry(): string {
  const expiry = new Date();
  expiry.setDate(expiry.getDate() + 7);
  return expiry.toISOString();
}

/**
 * Validate organization name
 */
function validateOrganizationName(name: unknown): { valid: boolean; error?: string } {
  if (typeof name !== "string") {
    return { valid: false, error: "Organization name must be a string" };
  }
  const trimmed = name.trim();
  if (trimmed.length < 2) {
    return { valid: false, error: "Organization name must be at least 2 characters" };
  }
  if (trimmed.length > 100) {
    return { valid: false, error: "Organization name must be less than 100 characters" };
  }
  return { valid: true };
}

/**
 * Validate role for updates
 */
function isValidRole(role: string): role is OrgRoleType {
  return Object.values(OrgRole).includes(role as OrgRoleType);
}

/**
 * Check if role can manage members
 */
function canManageMembers(role: OrgRoleType): boolean {
  return ORG_ROLE_HIERARCHY[role] >= ORG_ROLE_HIERARCHY.ADMIN;
}

/**
 * Check if role can delete organization
 */
function canDeleteOrg(role: OrgRoleType): boolean {
  return role === "OWNER";
}

/**
 * Require authentication helper
 */
async function requireAuth(
  c: { env: Env; req: { header: (name: string) => string | null; url: { pathname: string } } }
): Promise<{ success: true; userId: string; email: string; orgId: string; role: OrgRole } | { success: false; error: string; status: number }> {
  const apiKey = c.req.header("x-api-key");
  const authHeader = c.req.header("authorization");

  let result;
  if (apiKey) {
    result = await validateApiKey(c.env, apiKey);
  } else {
    result = await validateBearerToken(c.env, authHeader);
  }

  if (!result.success) {
    return { success: false, error: result.error, status: result.status };
  }

  return {
    success: true,
    userId: result.user.id,
    email: result.user.email,
    orgId: result.user.organizationId,
    role: result.user.role as OrgRole,
  };
}

// ============================================================================
// Route Definitions
// ============================================================================

const organizationsRoutes = new Hono<{ Bindings: Env }>();

// ============ Create Organization ============
// POST /organizations
organizationsRoutes.post("/", async (c) => {
  const db = getDb(c.env);
  const body = await c.req.json();

  // Validate request body
  const { valid, error } = validateOrganizationName(body.name);
  if (!valid) {
    return c.json({ error, code: "INVALID_NAME" }, 400);
  }

  const name = body.name.trim();
  const slug = body.slug || generateSlug(name);

  // Check if slug is already taken
  const [existingSlug] = await db
    .select()
    .from(organizations)
    .where(eq(organizations.slug, slug))
    .limit(1);

  if (existingSlug) {
    return c.json(
      { error: "Organization slug already exists", code: "SLUG_EXISTS" },
      409
    );
  }

  const now = new Date().toISOString();
  const orgId = uuidv4();

  // Create organization
  const [org] = await db
    .insert(organizations)
    .values({
      id: orgId,
      name,
      slug,
      logoUrl: body.logoUrl,
      settings: body.settings ? JSON.stringify(body.settings) : null,
      plan: body.plan || "free",
      createdAt: now,
      updatedAt: now,
    })
    .returning();

  // Add creator as owner
  await db.insert(organizationUsers).values({
    id: uuidv4(),
    organizationId: orgId,
    userId: body.userId || uuidv4(), // In production, this comes from auth
    email: body.email || "owner@example.com",
    role: OrgRole.OWNER,
    joinedAt: now,
    createdAt: now,
  });

  return c.json(
    {
      success: true,
      data: {
        ...org,
        settings: org.settings ? JSON.parse(org.settings) : null,
      },
    },
    201
  );
});

// ============ Get Organization ============
// GET /organizations/:id
organizationsRoutes.get("/:id", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");

  const [org] = await db
    .select()
    .from(organizations)
    .where(eq(organizations.id, id))
    .limit(1);

  if (!org) {
    return c.json({ error: "Organization not found", code: "NOT_FOUND" }, 404);
  }

  // Get member count
  const [memberCount] = await db
    .select({ count: sql<number>`count(*)` })
    .from(organizationUsers)
    .where(eq(organizationUsers.organizationId, id));

  return c.json({
    data: {
      ...org,
      settings: org.settings ? JSON.parse(org.settings) : null,
      memberCount: memberCount.count,
    },
  });
});

// ============ Update Organization ============
// PATCH /organizations/:id
organizationsRoutes.patch("/:id", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");
  const body = await c.req.json();

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  // Check if org exists
  const [existing] = await db
    .select()
    .from(organizations)
    .where(eq(organizations.id, id))
    .limit(1);

  if (!existing) {
    return c.json({ error: "Organization not found", code: "NOT_FOUND" }, 404);
  }

  // Only ADMIN or OWNER can update
  if (!hasMinimumRole(c, "ADMIN")) {
    return c.json(
      { error: "Insufficient permissions to update organization", code: "FORBIDDEN" },
      403
    );
  }

  const now = new Date().toISOString();
  const updates: Record<string, unknown> = { updatedAt: now };

  if (body.name !== undefined) {
    const { valid, error } = validateOrganizationName(body.name);
    if (!valid) {
      return c.json({ error, code: "INVALID_NAME" }, 400);
    }
    updates.name = body.name.trim();
  }

  if (body.logoUrl !== undefined) {
    updates.logoUrl = body.logoUrl;
  }

  if (body.settings !== undefined) {
    updates.settings = JSON.stringify(body.settings);
  }

  const [org] = await db
    .update(organizations)
    .set(updates)
    .where(eq(organizations.id, id))
    .returning();

  return c.json({
    success: true,
    data: {
      ...org,
      settings: org.settings ? JSON.parse(org.settings) : null,
    },
  });
});

// ============ Delete Organization ============
// DELETE /organizations/:id
organizationsRoutes.delete("/:id", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  // Check if org exists
  const [existing] = await db
    .select()
    .from(organizations)
    .where(eq(organizations.id, id))
    .limit(1);

  if (!existing) {
    return c.json({ error: "Organization not found", code: "NOT_FOUND" }, 404);
  }

  // Only OWNER can delete organization
  if (!isOwner(c)) {
    return c.json(
      { error: "Only OWNER can delete organization", code: "FORBIDDEN" },
      403
    );
  }

  // Delete organization (cascades to members and invitations)
  await db.delete(organizations).where(eq(organizations.id, id));

  return c.json({ success: true, message: "Organization deleted" });
});

// ============ List Members ============
// GET /organizations/:id/members
organizationsRoutes.get("/:id/members", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");

  // Check if org exists
  const [org] = await db
    .select()
    .from(organizations)
    .where(eq(organizations.id, id))
    .limit(1);

  if (!org) {
    return c.json({ error: "Organization not found", code: "NOT_FOUND" }, 404);
  }

  const members = await db
    .select()
    .from(organizationUsers)
    .where(eq(organizationUsers.organizationId, id))
    .orderBy(desc(organizationUsers.joinedAt));

  return c.json({
    data: members.map((m) => ({
      id: m.id,
      userId: m.userId,
      email: m.email,
      role: m.role,
      invitedAt: m.invitedAt,
      joinedAt: m.joinedAt,
      lastActiveAt: m.lastActiveAt,
    })),
    count: members.length,
  });
});

// ============ Update Member Role ============
// PATCH /organizations/:id/members/:userId
organizationsRoutes.patch("/:id/members/:userId", async (c) => {
  const db = getDb(c.env);
  const orgId = c.req.param("id");
  const userId = c.req.param("userId");
  const body = await c.req.json();

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  if (!body.role) {
    return c.json({ error: "Role is required", code: "INVALID_ROLE" }, 400);
  }

  if (!isValidRole(body.role)) {
    return c.json({ error: "Invalid role", code: "INVALID_ROLE" }, 400);
  }

  // Check if member exists
  const [member] = await db
    .select()
    .from(organizationUsers)
    .where(
      and(
        eq(organizationUsers.organizationId, orgId),
        eq(organizationUsers.userId, userId)
      )
    )
    .limit(1);

  if (!member) {
    return c.json({ error: "Member not found", code: "NOT_FOUND" }, 404);
  }

  // Cannot change OWNER role unless current user is OWNER
  if (member.role === OrgRole.OWNER && !isOwner(c)) {
    return c.json(
      { error: "Cannot modify OWNER role", code: "FORBIDDEN" },
      403
    );
  }

  // Only ADMIN or OWNER can change roles
  if (!canManageMembers(auth.role)) {
    return c.json(
      { error: "Insufficient permissions to update member roles", code: "FORBIDDEN" },
      403
    );
  }

  const [updated] = await db
    .update(organizationUsers)
    .set({ role: body.role })
    .where(
      and(
        eq(organizationUsers.organizationId, orgId),
        eq(organizationUsers.userId, userId)
      )
    )
    .returning();

  return c.json({
    success: true,
    data: {
      id: updated.id,
      userId: updated.userId,
      email: updated.email,
      role: updated.role,
    },
  });
});

// ============ Remove Member ============
// DELETE /organizations/:id/members/:userId
organizationsRoutes.delete("/:id/members/:userId", async (c) => {
  const db = getDb(c.env);
  const orgId = c.req.param("id");
  const userId = c.req.param("userId");

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  // Check if member exists
  const [member] = await db
    .select()
    .from(organizationUsers)
    .where(
      and(
        eq(organizationUsers.organizationId, orgId),
        eq(organizationUsers.userId, userId)
      )
    )
    .limit(1);

  if (!member) {
    return c.json({ error: "Member not found", code: "NOT_FOUND" }, 404);
  }

  // Cannot remove OWNER
  if (member.role === OrgRole.OWNER) {
    return c.json(
      { error: "Cannot remove OWNER from organization", code: "FORBIDDEN" },
      403
    );
  }

  // ADMIN+ can remove others, or user can remove themselves
  const isRemovingSelf = userId === auth.userId;
  if (!canManageMembers(auth.role) && !isRemovingSelf) {
    return c.json(
      { error: "Insufficient permissions to remove members", code: "FORBIDDEN" },
      403
    );
  }

  await db
    .delete(organizationUsers)
    .where(
      and(
        eq(organizationUsers.organizationId, orgId),
        eq(organizationUsers.userId, userId)
      )
    );

  return c.json({ success: true, message: "Member removed" });
});

// ============ Create Invitation ============
// POST /organizations/:id/invitations
organizationsRoutes.post("/:id/invitations", async (c) => {
  const db = getDb(c.env);
  const orgId = c.req.param("id");
  const body = await c.req.json();

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  // Only ADMIN or OWNER can invite
  if (!canManageMembers(auth.role)) {
    return c.json(
      { error: "Insufficient permissions to invite members", code: "FORBIDDEN" },
      403
    );
  }

  // Validate email
  if (!body.email || typeof body.email !== "string") {
    return c.json({ error: "Valid email is required", code: "INVALID_EMAIL" }, 400);
  }

  const email = body.email.toLowerCase().trim();
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    return c.json({ error: "Invalid email format", code: "INVALID_EMAIL" }, 400);
  }

  // Check if user is already a member
  const [existingMember] = await db
    .select()
    .from(organizationUsers)
    .where(
      and(
        eq(organizationUsers.organizationId, orgId),
        eq(organizationUsers.email, email)
      )
    )
    .limit(1);

  if (existingMember) {
    return c.json(
      { error: "User is already a member", code: "ALREADY_MEMBER" },
      409
    );
  }

  // Check for existing pending invitation
  const [existingInvite] = await db
    .select()
    .from(invitations)
    .where(
      and(
        eq(invitations.organizationId, orgId),
        eq(invitations.email, email),
        eq(invitations.status, InviteStatus.PENDING)
      )
    )
    .limit(1);

  if (existingInvite) {
    return c.json(
      { error: "Pending invitation already exists for this email", code: "INVITE_EXISTS" },
      409
    );
  }

  const role = isValidRole(body.role) ? body.role : OrgRole.USER;
  const token = generateInvitationToken();
  const expiresAt = getInvitationExpiry();
  const now = new Date().toISOString();

  const [invitation] = await db
    .insert(invitations)
    .values({
      id: uuidv4(),
      organizationId: orgId,
      email,
      role,
      token,
      status: InviteStatus.PENDING,
      invitedBy: auth.userId,
      expiresAt,
      createdAt: now,
    })
    .returning();

  // TODO: Send invitation email via email service

  return c.json(
    {
      success: true,
      data: {
        id: invitation.id,
        email: invitation.email,
        role: invitation.role,
        status: invitation.status,
        expiresAt: invitation.expiresAt,
        token: invitation.token, // Only shown once, in production send via email
      },
    },
    201
  );
});

// ============ List Invitations ============
// GET /organizations/:id/invitations
organizationsRoutes.get("/:id/invitations", async (c) => {
  const db = getDb(c.env);
  const orgId = c.req.param("id");

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  const status = c.req.query("status");
  let conditions = [eq(invitations.organizationId, orgId)];

  if (status && Object.values(InviteStatus).includes(status as InviteStatusType)) {
    conditions.push(eq(invitations.status, status as InviteStatusType));
  }

  const invites = await db
    .select()
    .from(invitations)
    .where(and(...conditions))
    .orderBy(desc(invitations.createdAt));

  return c.json({
    data: invites.map((inv) => ({
      id: inv.id,
      email: inv.email,
      role: inv.role,
      status: inv.status,
      invitedBy: inv.invitedBy,
      expiresAt: inv.expiresAt,
      acceptedAt: inv.acceptedAt,
      createdAt: inv.createdAt,
    })),
    count: invites.length,
  });
});

// ============ Accept Invitation ============
// POST /invitations/accept
organizationsRoutes.post("/invitations/accept", async (c) => {
  const db = getDb(c.env);
  const body = await c.req.json();

  // Validate token
  if (!body.token || typeof body.token !== "string") {
    return c.json({ error: "Invitation token is required", code: "INVALID_TOKEN" }, 400);
  }

  // Find invitation
  const [invitation] = await db
    .select()
    .from(invitations)
    .where(eq(invitations.token, body.token))
    .limit(1);

  if (!invitation) {
    return c.json({ error: "Invalid invitation", code: "NOT_FOUND" }, 404);
  }

  // Check invitation status
  if (invitation.status !== InviteStatus.PENDING) {
    return c.json(
      { error: `Invitation has already been ${invitation.status.toLowerCase()}`, code: "INVALID_STATUS" },
      400
    );
  }

  // Check expiration
  if (new Date(invitation.expiresAt) < new Date()) {
    await db
      .update(invitations)
      .set({ status: InviteStatus.EXPIRED })
      .where(eq(invitations.id, invitation.id));
    return c.json({ error: "Invitation has expired", code: "EXPIRED" }, 400);
  }

  // Check if user is already a member (shouldn't happen due to earlier check)
  const [existingMember] = await db
    .select()
    .from(organizationUsers)
    .where(
      and(
        eq(organizationUsers.organizationId, invitation.organizationId),
        eq(organizationUsers.email, invitation.email)
      )
    )
    .limit(1);

  if (existingMember) {
    await db
      .update(invitations)
      .set({ status: InviteStatus.ACCEPTED })
      .where(eq(invitations.id, invitation.id));
    return c.json(
      { error: "User is already a member", code: "ALREADY_MEMBER" },
      409
    );
  }

  const now = new Date().toISOString();
  const userId = body.userId || uuidv4(); // In production, from auth

  // Add user as member
  await db.insert(organizationUsers).values({
    id: uuidv4(),
    organizationId: invitation.organizationId,
    userId,
    email: invitation.email,
    role: invitation.role,
    joinedAt: now,
    createdAt: now,
  });

  // Update invitation status
  await db
    .update(invitations)
    .set({
      status: InviteStatus.ACCEPTED,
      acceptedAt: now,
    })
    .where(eq(invitations.id, invitation.id));

  // Get organization details
  const [org] = await db
    .select()
    .from(organizations)
    .where(eq(organizations.id, invitation.organizationId))
    .limit(1);

  return c.json({
    success: true,
    data: {
      userId,
      email: invitation.email,
      organizationId: invitation.organizationId,
      organizationName: org?.name,
      role: invitation.role,
      message: "Successfully joined organization",
    },
  });
});

// ============ Revoke Invitation ============
// DELETE /organizations/:id/invitations/:inviteId
organizationsRoutes.delete("/:id/invitations/:inviteId", async (c) => {
  const db = getDb(c.env);
  const orgId = c.req.param("id");
  const inviteId = c.req.param("inviteId");

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  // Only ADMIN or OWNER can revoke invitations
  if (!canManageMembers(auth.role)) {
    return c.json(
      { error: "Insufficient permissions to revoke invitations", code: "FORBIDDEN" },
      403
    );
  }

  // Check if invitation exists
  const [invitation] = await db
    .select()
    .from(invitations)
    .where(
      and(
        eq(invitations.id, inviteId),
        eq(invitations.organizationId, orgId)
      )
    )
    .limit(1);

  if (!invitation) {
    return c.json({ error: "Invitation not found", code: "NOT_FOUND" }, 404);
  }

  if (invitation.status !== InviteStatus.PENDING) {
    return c.json(
      { error: "Can only revoke pending invitations", code: "INVALID_STATUS" },
      400
    );
  }

  await db
    .update(invitations)
    .set({ status: InviteStatus.REVOKED })
    .where(eq(invitations.id, inviteId));

  return c.json({ success: true, message: "Invitation revoked" });
});

export { organizationsRoutes };
