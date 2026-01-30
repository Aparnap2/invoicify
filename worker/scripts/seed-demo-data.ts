/**
 * Demo Data Seeding Script - TDD Style
 *
 * Seeds Neo4j and D1 with realistic demo data for testing:
 * - Vendors with varying trust levels
 * - Invoice history with temporal patterns
 * - Approval workflows
 * - Risk indicators
 *
 * Run: npx tsx scripts/seed-demo-data.ts
 */

import { v4 as uuidv4 } from "uuid";
import { getDb, schema } from "../src/db";

// ============================================================================
// TYPES
// ============================================================================

interface DemoVendor {
  id: string;
  name: string;
  category: string;
  trustScore: number;
  riskLevel: "LOW" | "MEDIUM" | "HIGH";
  avgInvoiceAmount: number;
  totalInvoices: number;
  consecutiveAccurate: number;
  onTimeRate: number;
}

interface DemoInvoice {
  id: string;
  invoiceNumber: string;
  vendorId: string;
  amount: number;
  currency: string;
  status: string;
  riskScore: number;
  riskLevel: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  riskSignals: string[];
  dueDate: string;
  invoiceDate: string;
  category: string;
}

interface DemoLineItem {
  id: string;
  invoiceId: string;
  description: string;
  quantity: number;
  unitPrice: number;
  amount: number;
  glCode: string;
}

// ============================================================================
// DEMO DATA SETS
// ============================================================================

const DEMO_VENDORS: DemoVendor[] = [
  {
    id: "vendor-001",
    name: "Acme Office Supplies",
    category: "office_supplies",
    trustScore: 0.92,
    riskLevel: "LOW",
    avgInvoiceAmount: 2500,
    totalInvoices: 47,
    consecutiveAccurate: 85,
    onTimeRate: 0.96,
  },
  {
    id: "vendor-002",
    name: "Tech Solutions Inc",
    category: "software",
    trustScore: 0.78,
    riskLevel: "MEDIUM",
    avgInvoiceAmount: 15000,
    totalInvoices: 23,
    consecutiveAccurate: 52,
    onTimeRate: 0.88,
  },
  {
    id: "vendor-003",
    name: "Global Logistics LLC",
    category: "shipping",
    trustScore: 0.95,
    riskLevel: "LOW",
    avgInvoiceAmount: 3200,
    totalInvoices: 156,
    consecutiveAccurate: 120,
    onTimeRate: 0.98,
  },
  {
    id: "vendor-004",
    name: "Rapid Parts Co",
    category: "manufacturing",
    trustScore: 0.65,
    riskLevel: "MEDIUM",
    avgInvoiceAmount: 8500,
    totalInvoices: 12,
    consecutiveAccurate: 15,
    onTimeRate: 0.75,
  },
  {
    id: "vendor-005",
    name: "Suspicious Vendor LLC",
    category: "consulting",
    trustScore: 0.25,
    riskLevel: "HIGH",
    avgInvoiceAmount: 25000,
    totalInvoices: 3,
    consecutiveAccurate: 0,
    onTimeRate: 0.33,
  },
  {
    id: "vendor-006",
    name: "Startup Services",
    category: "professional_services",
    trustScore: 0.55,
    riskLevel: "MEDIUM",
    avgInvoiceAmount: 5500,
    totalInvoices: 8,
    consecutiveAccurate: 12,
    onTimeRate: 0.80,
  },
];

const TODAY = new Date();
const GET_DATE_DAYS = (days: number) => {
  const d = new Date(TODAY);
  d.setDate(d.getDate() + days);
  return d.toISOString().split("T")[0];
};

const DEMO_INVOICES: DemoInvoice[] = [
  // Low risk, high trust vendor invoices
  {
    id: "invoice-001",
    invoiceNumber: "INV-2024-001",
    vendorId: "vendor-001",
    amount: 2450.0,
    currency: "USD",
    status: "PENDING",
    riskScore: 0.15,
    riskLevel: "LOW",
    riskSignals: [],
    dueDate: GET_DATE_DAYS(30),
    invoiceDate: GET_DATE_DAYS(-2),
    category: "office_supplies",
  },
  {
    id: "invoice-002",
    invoiceNumber: "INV-2024-002",
    vendorId: "vendor-001",
    amount: 890.0,
    currency: "USD",
    status: "PENDING",
    riskScore: 0.10,
    riskLevel: "LOW",
    riskSignals: [],
    dueDate: GET_DATE_DAYS(25),
    invoiceDate: GET_DATE_DAYS(-5),
    category: "office_supplies",
  },
  // Medium risk vendor invoices
  {
    id: "invoice-003",
    invoiceNumber: "INV-2024-003",
    vendorId: "vendor-002",
    amount: 15750.0,
    currency: "USD",
    status: "PENDING",
    riskScore: 0.52,
    riskLevel: "MEDIUM",
    riskSignals: ["Amount 5% above vendor average", "End of quarter timing"],
    dueDate: GET_DATE_DAYS(15),
    invoiceDate: GET_DATE_DAYS(-15),
    category: "software",
  },
  {
    id: "invoice-004",
    invoiceNumber: "INV-2024-004",
    vendorId: "vendor-002",
    amount: 2800.0,
    currency: "USD",
    status: "PENDING",
    riskScore: 0.28,
    riskLevel: "LOW",
    riskSignals: [],
    dueDate: GET_DATE_DAYS(20),
    invoiceDate: GET_DATE_DAYS(-10),
    category: "software",
  },
  // High trust logistics vendor
  {
    id: "invoice-005",
    invoiceNumber: "INV-2024-005",
    vendorId: "vendor-003",
    amount: 3200.0,
    currency: "USD",
    status: "PENDING",
    riskScore: 0.12,
    riskLevel: "LOW",
    riskSignals: [],
    dueDate: GET_DATE_DAYS(14),
    invoiceDate: GET_DATE_DAYS(-4),
    category: "shipping",
  },
  // Lower trust vendor with issues
  {
    id: "invoice-006",
    invoiceNumber: "INV-2024-006",
    vendorId: "vendor-004",
    amount: 12500.0,
    currency: "USD",
    status: "PENDING",
    riskScore: 0.68,
    riskLevel: "HIGH",
    riskSignals: [
      "New vendor (3rd invoice)",
      "Amount 47% above average",
      "Late delivery on previous order",
    ],
    dueDate: GET_DATE_DAYS(10),
    invoiceDate: GET_DATE_DAYS(-20),
    category: "manufacturing",
  },
  // Suspicious vendor - HIGH RISK
  {
    id: "invoice-007",
    invoiceNumber: "INV-2024-007",
    vendorId: "vendor-005",
    amount: 45000.0,
    currency: "USD",
    status: "NEW",
    riskScore: 0.89,
    riskLevel: "CRITICAL",
    riskSignals: [
      "New vendor with no history",
      "Amount 80% above average",
      "Requesting immediate payment",
      "Generic invoice description",
      "PO number mismatch",
    ],
    dueDate: GET_DATE_DAYS(10),
    invoiceDate: GET_DATE_DAYS(-3),
    category: "consulting",
  },
  // Startup services - medium risk
  {
    id: "invoice-008",
    invoiceNumber: "INV-2024-008",
    vendorId: "vendor-006",
    amount: 7500.0,
    currency: "USD",
    status: "PENDING",
    riskScore: 0.45,
    riskLevel: "MEDIUM",
    riskSignals: ["Contract renewal period", "Rate increased 10%"],
    dueDate: GET_DATE_DAYS(21),
    invoiceDate: GET_DATE_DAYS(-9),
    category: "professional_services",
  },
];

const DEMO_LINE_ITEMS: DemoLineItem[] = [
  {
    id: "li-001",
    invoiceId: "invoice-001",
    description: "Ergonomic Office Chairs",
    quantity: 5,
    unitPrice: 350,
    amount: 1750,
    glCode: "6500-001",
  },
  {
    id: "li-002",
    invoiceId: "invoice-001",
    description: "Standing Desk Converters",
    quantity: 2,
    unitPrice: 350,
    amount: 700,
    glCode: "6500-002",
  },
  {
    id: "li-003",
    invoiceId: "invoice-002",
    description: "Printer Paper (cases)",
    quantity: 20,
    unitPrice: 44.5,
    amount: 890,
    glCode: "6200-001",
  },
  {
    id: "li-004",
    invoiceId: "invoice-003",
    description: "Enterprise Software License - Annual",
    quantity: 1,
    unitPrice: 15750,
    amount: 15750,
    glCode: "7200-001",
  },
];

// ============================================================================
// SEED FUNCTIONS
// ============================================================================

/**
 * Clear existing demo data (for clean re-seeding)
 */
export async function clearDemoData(env: Env): Promise<void> {
  const db = getDb(env);

  // Delete in reverse order of dependencies
  await db.delete(schema.riskIndicators).where(
    undefined // Delete all
  );
  await db.delete(schema.lineItems).where(undefined);
  await db.delete(schema.approvals).where(undefined);
  await db.delete(schema.agentDecisions).where(undefined);
  await db.delete(schema.trustBattery).where(undefined);
  await db.delete(schema.invoices).where(undefined);
  await db.delete(schema.vendors).where(undefined);

  console.log("Cleared existing demo data from D1");
}

/**
 * Seed vendors table
 */
export async function seedVendors(env: Env): Promise<void> {
  const db = getDb(env);

  for (const vendor of DEMO_VENDORS) {
    await db.insert(schema.vendors).values({
      id: vendor.id,
      name: vendor.name,
      taxId: `TAX-${vendor.id.slice(-8).toUpperCase()}`,
      email: `finance@${vendor.name.toLowerCase().replace(/\s+/g, "")}.com`,
      phone: "+1-555-0100",
      address: "123 Business St, San Francisco, CA 94102",
      isVerified: vendor.trustScore > 0.7,
      riskLevel: vendor.riskLevel,
      avgInvoiceAmount: vendor.avgInvoiceAmount,
      totalInvoices: vendor.totalInvoices,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });

    // Seed trust battery for each vendor
    await db.insert(schema.trustBattery).values({
      id: uuidv4(),
      vendorId: vendor.id,
      consecutiveAccurate: vendor.consecutiveAccurate,
      consecutiveErrors: 0,
      totalDecisions: vendor.totalInvoices,
      accurateDecisions: Math.floor(vendor.totalInvoices * (vendor.onTimeRate)),
      trustLevel: vendor.trustScore > 0.85 ? 3 : vendor.trustScore > 0.6 ? 2 : 1,
      autoApproveThreshold: vendor.trustScore > 0.85 ? 5000 : vendor.trustScore > 0.6 ? 500 : 0,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
  }

  console.log(`Seeded ${DEMO_VENDORS.length} vendors`);
}

/**
 * Seed invoices table
 */
export async function seedInvoices(env: Env): Promise<void> {
  const db = getDb(env);

  for (const invoice of DEMO_INVOICES) {
    await db.insert(schema.invoices).values({
      id: invoice.id,
      vendorId: invoice.vendorId,
      vendorName: DEMO_VENDORS.find((v) => v.id === invoice.vendorId)?.name || "",
      invoiceNumber: invoice.invoiceNumber,
      totalAmount: invoice.amount,
      currency: invoice.currency,
      status: invoice.status as any,
      riskScore: invoice.riskScore,
      riskLevel: invoice.riskLevel,
      dueDate: invoice.dueDate,
      invoiceDate: invoice.invoiceDate,
      category: invoice.category,
      confidenceScore: 1.0 - invoice.riskScore,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });

    // Seed risk indicators for this invoice
    for (const signal of invoice.riskSignals) {
      const severity =
        invoice.riskLevel === "CRITICAL"
          ? "CRITICAL"
          : invoice.riskLevel === "HIGH"
            ? "HIGH"
            : invoice.riskLevel === "MEDIUM"
              ? "MEDIUM"
              : "LOW";

      await db.insert(schema.riskIndicators).values({
        id: uuidv4(),
        invoiceId: invoice.id,
        indicatorType: signal.includes("above") ? "AMOUNT_DEVIATION" : signal.includes("New") ? "NEW_VENDOR" : signal.includes("timing") ? "TIMING_PATTERN" : "OTHER",
        severity,
        description: signal,
        scoreContribution: invoice.riskScore / invoice.riskSignals.length,
        createdAt: new Date().toISOString(),
      });
    }
  }

  console.log(`Seeded ${DEMO_INVOICES.length} invoices`);
}

/**
 * Seed line items
 */
export async function seedLineItems(env: Env): Promise<void> {
  const db = getDb(env);

  for (const item of DEMO_LINE_ITEMS) {
    await db.insert(schema.lineItems).values({
      id: item.id,
      invoiceId: item.invoiceId,
      description: item.description,
      quantity: item.quantity,
      unitPrice: item.unitPrice,
      amount: item.amount,
      glCode: item.glCode,
      createdAt: new Date().toISOString(),
    });
  }

  console.log(`Seeded ${DEMO_LINE_ITEMS.length} line items`);
}

/**
 * Seed Neo4j with graph data
 */
export async function seedNeo4j(): Promise<void> {
  const neo4jUrl = process.env.NEO4J_URL || "bolt://localhost:7687";
  const neo4jUser = process.env.NEO4J_USER || "neo4j";
  const neo4jPassword = process.env.NEO4J_PASSWORD;

  if (!neo4jPassword) {
    console.log("NEO4J_PASSWORD not set, skipping Neo4j seeding");
    return;
  }

  // Dynamic import for neo4j driver
  let driver: any;
  try {
    const neo4j = await import("neo4j-driver");
    driver = neo4j.default.driver(neo4jUrl, neo4j.default.auth.basic(neo4jUser, neo4jPassword));
  } catch (e) {
    console.log("Neo4j driver not available, skipping graph seeding");
    return;
  }

  const session = driver.session();

  try {
    // Clear existing data
    await session.run("MATCH (n) DETACH DELETE n");
    console.log("Cleared existing Neo4j data");

    // Create indexes (idempotent)
    await session.run("CREATE INDEX vendor_id_idx IF NOT EXISTS FOR (v:Vendor) ON (v.id)");
    await session.run("CREATE INDEX invoice_id_idx IF NOT EXISTS FOR (i:Invoice) ON (i.id)");
    await session.run("CREATE INDEX invoice_status_idx IF NOT EXISTS FOR (i:Invoice) ON (i.status)");
    console.log("Created Neo4j indexes");

    // Seed vendors with temporal trust history
    for (const vendor of DEMO_VENDORS) {
      await session.run(
        `CREATE (v:Vendor {
          id: $id,
          name: $name,
          category: $category,
          trust_score: $trustScore,
          risk_level: $riskLevel,
          avg_invoice_amount: $avgAmount,
          total_invoices: $totalInvoices,
          consecutive_accurate: $consecutiveAccurate,
          on_time_rate: $onTimeRate,
          created_at: datetime()
        })`,
        {
          id: vendor.id,
          name: vendor.name,
          category: vendor.category,
          trustScore: vendor.trustScore,
          riskLevel: vendor.riskLevel,
          avgAmount: vendor.avgInvoiceAmount,
          totalInvoices: vendor.totalInvoices,
          consecutiveAccurate: vendor.consecutiveAccurate,
          onTimeRate: vendor.onTimeRate,
        }
      );

      // Add temporal trust history (last 3 months)
      const now = Date.now();
      const monthMs = 30 * 24 * 60 * 60 * 1000;
      for (let i = 0; i < 3; i++) {
        const score = Math.max(0.3, vendor.trustScore - (i * 0.05) + (Math.random() * 0.1));
        await session.run(
          `MATCH (v:Vendor {id: $id})
           CREATE (v)-[:TRUST_HISTORY {
             from: $from,
             to: $to,
             score: $score
           }]->(:TrustPoint {value: $score})`,
          {
            id: vendor.id,
            from: now - ((i + 1) * monthMs),
            to: now - (i * monthMs),
            score: score,
          }
        );
      }
    }
    console.log("Seeded vendors in Neo4j");

    // Seed invoices with relationships
    for (const invoice of DEMO_INVOICES) {
      await session.run(
        `CREATE (i:Invoice {
          id: $id,
          invoice_number: $invoiceNumber,
          amount: $amount,
          currency: $currency,
          status: $status,
          risk_score: $riskScore,
          risk_level: $riskLevel,
          due_date: $dueDate,
          invoice_date: $invoiceDate,
          category: $category,
          created_at: datetime()
        })`,
        {
          id: invoice.id,
          invoiceNumber: invoice.invoiceNumber,
          amount: invoice.amount,
          currency: invoice.currency,
          status: invoice.status,
          riskScore: invoice.riskScore,
          riskLevel: invoice.riskLevel,
          dueDate: invoice.dueDate,
          invoiceDate: invoice.invoiceDate,
          category: invoice.category,
        }
      );

      // Link to vendor
      await session.run(
        `MATCH (v:Vendor {id: $vendorId})
         MATCH (i:Invoice {id: $invoiceId})
         CREATE (v)-[:ISSUED {
           issued_at: datetime($invoiceDate),
           amount: $amount
         }]->(i)`,
        {
          vendorId: invoice.vendorId,
          invoiceId: invoice.id,
          invoiceDate: invoice.invoiceDate,
          amount: invoice.amount,
        }
      );

      // Add risk signals as related nodes
      for (const signal of invoice.riskSignals) {
        await session.run(
          `MATCH (i:Invoice {id: $invoiceId})
           CREATE (r:RiskSignal {
             id: $signalId,
             description: $description,
             severity: $severity,
             detected_at: datetime()
           })
           CREATE (i)-[:HAS_SIGNAL {weight: $weight}]->(r)`,
          {
            invoiceId: invoice.id,
            signalId: `signal-${invoice.id}-${signal.slice(0, 10)}`,
            description: signal,
            severity: invoice.riskLevel,
            weight: invoice.riskScore / invoice.riskSignals.length,
          }
        );
      }
    }
    console.log("Seeded invoices and relationships in Neo4j");

    // Create temporal patterns (recurring invoices)
    await session.run(
      `MATCH (v:Vendor {id: 'vendor-001'})-[:ISSUED]->(i1:Invoice)
       MATCH (v)-[:ISSUED]->(i2:Invoice)
       WHERE i1 <> i2 AND i1.invoice_date < i2.invoice_date
       CREATE (i1)-[:FOLLOWS {days_between: duration.between(date(i1.invoice_date), date(i2.invoice_date)).days}]->(i2)`
    );
    console.log("Created temporal patterns in Neo4j");

  } finally {
    await session.close();
    await driver.close();
  }
}

// ============================================================================
// MAIN
// ============================================================================

/**
 * Run full demo data seeding
 */
export async function seedDemoData(env: Env): Promise<{
  vendors: number;
  invoices: number;
  lineItems: number;
  neo4j: boolean;
}> {
  console.log("Starting demo data seeding...\n");

  // Seed D1 tables
  await clearDemoData(env);
  await seedVendors(env);
  await seedInvoices(env);
  await seedLineItems(env);

  // Seed Neo4j
  let neo4jSuccess = false;
  try {
    await seedNeo4j();
    neo4jSuccess = true;
  } catch (error) {
    console.error("Neo4j seeding failed:", error);
  }

  console.log("\nDemo data seeding complete!");
  return {
    vendors: DEMO_VENDORS.length,
    invoices: DEMO_INVOICES.length,
    lineItems: DEMO_LINE_ITEMS.length,
    neo4j: neo4jSuccess,
  };
}

// ============================================================================
// TESTS (TDD)
// ============================================================================

import { describe, it, expect, beforeAll, afterAll } from "vitest";

describe("Demo Data Seeding", () => {
  describe("Demo Data Structure", () => {
    it("should have valid vendor trust scores (0-1)", () => {
      for (const vendor of DEMO_VENDORS) {
        expect(vendor.trustScore).toBeGreaterThanOrEqual(0);
        expect(vendor.trustScore).toBeLessThanOrEqual(1);
      }
    });

    it("should have at least one vendor per risk level", () => {
      const riskLevels = new Set(DEMO_VENDORS.map((v) => v.riskLevel));
      expect(riskLevels.has("LOW")).toBe(true);
      expect(riskLevels.has("MEDIUM")).toBe(true);
      expect(riskLevels.has("HIGH")).toBe(true);
    });

    it("should have invoices with varying risk levels", () => {
      const riskLevels = new Set(DEMO_INVOICES.map((i) => i.riskLevel));
      expect(riskLevels.has("LOW")).toBe(true);
      expect(riskLevels.has("MEDIUM")).toBe(true);
      expect(riskLevels.has("HIGH")).toBe(true);
      expect(riskLevels.has("CRITICAL")).toBe(true);
    });

    it("should have risk scores that correlate with risk levels", () => {
      for (const invoice of DEMO_INVOICES) {
        if (invoice.riskLevel === "LOW") {
          expect(invoice.riskScore).toBeLessThan(0.3);
        } else if (invoice.riskLevel === "MEDIUM") {
          expect(invoice.riskScore).toBeGreaterThanOrEqual(0.3);
          expect(invoice.riskScore).toBeLessThan(0.6);
        } else if (invoice.riskLevel === "HIGH") {
          expect(invoice.riskScore).toBeGreaterThanOrEqual(0.6);
          expect(invoice.riskScore).toBeLessThan(0.85);
        } else if (invoice.riskLevel === "CRITICAL") {
          expect(invoice.riskScore).toBeGreaterThanOrEqual(0.85);
        }
      }
    });

    it("should have vendors with sufficient history for trust battery", () => {
      for (const vendor of DEMO_VENDORS) {
        if (vendor.trustScore > 0.7) {
          expect(vendor.consecutiveAccurate).toBeGreaterThanOrEqual(50);
        }
      }
    });

    it("should have line items that match invoice amounts", () => {
      for (const invoice of DEMO_INVOICES) {
        const items = DEMO_LINE_ITEMS.filter((li) => li.invoiceId === invoice.id);
        if (items.length > 0) {
          const calculatedTotal = items.reduce((sum, li) => sum + li.amount, 0);
          expect(calculatedTotal).toBeLessThanOrEqual(invoice.amount);
        }
      }
    });

    it("should have realistic due dates (7-45 days from now)", () => {
      const now = Date.now();
      const dayMs = 24 * 60 * 60 * 1000;

      for (const invoice of DEMO_INVOICES) {
        const dueDate = new Date(invoice.dueDate).getTime();
        const daysUntilDue = (dueDate - now) / dayMs;
        expect(daysUntilDue).toBeGreaterThanOrEqual(7);
        expect(daysUntilDue).toBeLessThanOrEqual(45);
      }
    });
  });
});

// Run if executed directly (ESM-compatible)
import { fileURLToPath } from "url";
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  // Note: This would need proper env setup to run
  console.log("Run tests with: bun test scripts/seed-demo-data.ts");
}
