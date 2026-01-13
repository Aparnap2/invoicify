import { Hono } from "hono";
import { getDb, schema } from "../db";
import { sql } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import { seedNeo4jGraph, getNeo4jStatus } from "../lib/neo4j";
import type { Env } from "../db";

const seedRoutes = new Hono<{ Bindings: Env }>();

// Demo vendors
const DEMO_VENDORS = [
  { id: "vendor-001", name: "Acme Office Supplies", category: "office_supplies", trustScore: 0.92, riskLevel: "LOW", avgInvoiceAmount: 2500, totalInvoices: 47, consecutiveAccurate: 85 },
  { id: "vendor-002", name: "Tech Solutions Inc", category: "software", trustScore: 0.78, riskLevel: "MEDIUM", avgInvoiceAmount: 15000, totalInvoices: 23, consecutiveAccurate: 52 },
  { id: "vendor-003", name: "Global Logistics LLC", category: "shipping", trustScore: 0.95, riskLevel: "LOW", avgInvoiceAmount: 3200, totalInvoices: 156, consecutiveAccurate: 120 },
  { id: "vendor-004", name: "Rapid Parts Co", category: "manufacturing", trustScore: 0.65, riskLevel: "MEDIUM", avgInvoiceAmount: 8500, totalInvoices: 12, consecutiveAccurate: 15 },
  { id: "vendor-005", name: "Suspicious Vendor LLC", category: "consulting", trustScore: 0.25, riskLevel: "HIGH", avgInvoiceAmount: 25000, totalInvoices: 3, consecutiveAccurate: 0 },
  { id: "vendor-006", name: "Startup Services", category: "professional_services", trustScore: 0.55, riskLevel: "MEDIUM", avgInvoiceAmount: 5500, totalInvoices: 8, consecutiveAccurate: 12 },
];

const TODAY = new Date();
const GET_DATE_DAYS = (days: number) => {
  const d = new Date(TODAY);
  d.setDate(d.getDate() + days);
  return d.toISOString().split("T")[0];
};

// Demo invoices
const DEMO_INVOICES = [
  { id: "invoice-001", invoiceNumber: "INV-2024-001", vendorId: "vendor-001", amount: 2450, riskScore: 0.15, riskLevel: "LOW", status: "PENDING", category: "office_supplies", riskSignals: [] },
  { id: "invoice-002", invoiceNumber: "INV-2024-002", vendorId: "vendor-001", amount: 890, riskScore: 0.10, riskLevel: "LOW", status: "PENDING", category: "office_supplies", riskSignals: [] },
  { id: "invoice-003", invoiceNumber: "INV-2024-003", vendorId: "vendor-002", amount: 15750, riskScore: 0.52, riskLevel: "MEDIUM", status: "PENDING", category: "software", riskSignals: ["Amount 5% above vendor average", "End of quarter timing"] },
  { id: "invoice-004", invoiceNumber: "INV-2024-004", vendorId: "vendor-002", amount: 2800, riskScore: 0.28, riskLevel: "LOW", status: "PENDING", category: "software", riskSignals: [] },
  { id: "invoice-005", invoiceNumber: "INV-2024-005", vendorId: "vendor-003", amount: 3200, riskScore: 0.12, riskLevel: "LOW", status: "PENDING", category: "shipping", riskSignals: [] },
  { id: "invoice-006", invoiceNumber: "INV-2024-006", vendorId: "vendor-004", amount: 12500, riskScore: 0.68, riskLevel: "HIGH", status: "PENDING", category: "manufacturing", riskSignals: ["New vendor (3rd invoice)", "Amount 47% above average", "Late delivery on previous order"] },
  { id: "invoice-007", invoiceNumber: "INV-2024-007", vendorId: "vendor-005", amount: 45000, riskScore: 0.89, riskLevel: "CRITICAL", status: "NEW", category: "consulting", riskSignals: ["New vendor with no history", "Amount 80% above average", "Requesting immediate payment", "Generic invoice description", "PO number mismatch"] },
  { id: "invoice-008", invoiceNumber: "INV-2024-008", vendorId: "vendor-006", amount: 7500, riskScore: 0.45, riskLevel: "MEDIUM", status: "PENDING", category: "professional_services", riskSignals: ["Contract renewal period", "Rate increased 10%"] },
];

// POST /api/v1/seed/demo - Seed demo data
seedRoutes.post("/demo", async (c) => {
  const db = getDb(c.env);
  const result: { vendors: number; invoices: number; riskIndicators: number } = { vendors: 0, invoices: 0, riskIndicators: 0 };

  // Clear existing data
  await db.delete(schema.riskIndicators);
  await db.delete(schema.lineItems);
  await db.delete(schema.approvals);
  await db.delete(schema.agentDecisions);
  await db.delete(schema.trustBattery);
  await db.delete(schema.invoices);
  await db.delete(schema.vendors);

  // Seed vendors
  for (const v of DEMO_VENDORS) {
    await db.insert(schema.vendors).values({
      id: v.id,
      name: v.name,
      taxId: `TAX-${v.id.slice(-8).toUpperCase()}`,
      email: `finance@${v.name.toLowerCase().replace(/\s+/g, "")}.com`,
      isVerified: v.trustScore > 0.7,
      riskLevel: v.riskLevel,
      avgInvoiceAmount: v.avgInvoiceAmount,
      totalInvoices: v.totalInvoices,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });

    await db.insert(schema.trustBattery).values({
      id: uuidv4(),
      vendorId: v.id,
      consecutiveAccurate: v.consecutiveAccurate,
      consecutiveErrors: 0,
      totalDecisions: v.totalInvoices,
      accurateDecisions: Math.floor(v.totalInvoices * 0.9),
      trustLevel: v.trustScore > 0.85 ? 3 : v.trustScore > 0.6 ? 2 : 1,
      autoApproveThreshold: v.trustScore > 0.85 ? 5000 : v.trustScore > 0.6 ? 500 : 0,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    result.vendors++;
  }

  // Seed invoices
  for (const inv of DEMO_INVOICES) {
    const vendor = DEMO_VENDORS.find((v) => v.id === inv.vendorId);
    await db.insert(schema.invoices).values({
      id: inv.id,
      vendorId: inv.vendorId,
      vendorName: vendor?.name || "",
      invoiceNumber: inv.invoiceNumber,
      totalAmount: inv.amount,
      currency: "USD",
      status: inv.status as any,
      riskScore: inv.riskScore,
      riskLevel: inv.riskLevel,
      dueDate: GET_DATE_DAYS(30),
      invoiceDate: GET_DATE_DAYS(0),
      category: inv.category,
      confidenceScore: 1.0 - inv.riskScore,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });

    // Seed risk indicators
    for (const signal of inv.riskSignals) {
      const severity = inv.riskLevel === "CRITICAL" ? "CRITICAL" : inv.riskLevel === "HIGH" ? "HIGH" : inv.riskLevel === "MEDIUM" ? "MEDIUM" : "LOW";
      await db.insert(schema.riskIndicators).values({
        id: uuidv4(),
        invoiceId: inv.id,
        indicatorType: signal.includes("above") ? "AMOUNT_DEVIATION" : signal.includes("New") ? "NEW_VENDOR" : "OTHER",
        severity,
        description: signal,
        scoreContribution: inv.riskScore / Math.max(inv.riskSignals.length, 1),
        createdAt: new Date().toISOString(),
      });
      result.riskIndicators++;
    }
    result.invoices++;
  }

  return c.json({
    success: true,
    message: "Demo data seeded successfully",
    data: result,
  });
});

// GET /api/v1/seed/status - Check seeding status
seedRoutes.get("/status", async (c) => {
  const db = getDb(c.env);

  const [vendorCount] = await db.select({ count: sql<number>`count(*)` }).from(schema.vendors);
  const [invoiceCount] = await db.select({ count: sql<number>`count(*)` }).from(schema.invoices);
  const [riskCount] = await db.select({ count: sql<number>`count(*)` }).from(schema.riskIndicators);

  return c.json({
    vendors: Number(vendorCount?.count) || 0,
    invoices: Number(invoiceCount?.count) || 0,
    riskIndicators: Number(riskCount?.count) || 0,
  });
});

// POST /api/v1/seed/neo4j - Seed Neo4j graph
seedRoutes.post("/neo4j", async (c) => {
  try {
    const result = await seedNeo4jGraph();
    return c.json({
      success: true,
      message: "Neo4j graph seeded successfully",
      data: result,
    });
  } catch (error: any) {
    return c.json({ success: false, error: error.message }, 500);
  }
});

// GET /api/v1/seed/neo4j/status - Check Neo4j status
seedRoutes.get("/neo4j/status", async (c) => {
  const status = await getNeo4jStatus();
  return c.json(status);
});

export { seedRoutes };
