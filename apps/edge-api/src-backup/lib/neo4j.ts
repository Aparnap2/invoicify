/**
 * Neo4j Graph Database Client
 *
 * Uses official neo4j-driver for graph operations.
 * Drizzle ORM does NOT support Neo4j - it only supports SQL databases.
 *
 * NOTE: In Cloudflare Workers, we create a new driver per request and close it
 * after each operation. This is required because Workers don't allow sharing
 * I/O objects across requests.
 */

import neo4j from "neo4j-driver";

const NEO4J_URI = process.env.NEO4J_URI || "bolt://localhost:7687";
const NEO4J_USER = process.env.NEO4J_USER || "neo4j";
const NEO4J_PASSWORD = process.env.NEO4J_PASSWORD || "founderos_secret";

/**
 * Create a new Neo4j driver (call per-request in Workers)
 */
function createDriver(): neo4j.Driver {
  return neo4j.driver(NEO4J_URI, neo4j.auth.basic(NEO4J_USER, NEO4J_PASSWORD));
}

/**
 * Execute a Cypher query with parameters
 */
export async function executeCypher(
  query: string,
  params: Record<string, any> = {}
): Promise<neo4j.QueryResult> {
  const driver = createDriver();
  const session = driver.session();
  try {
    return await session.run(query, params);
  } finally {
    await session.close();
    await driver.close();
  }
}

/**
 * Seed the Neo4j graph with demo data
 */
export async function seedNeo4jGraph(): Promise<{ nodes: number; relationships: number }> {
  const driver = createDriver();
  const session = driver.session();
  let nodes = 0;
  let relationships = 0;

  try {
    // Clear existing data
    await session.run("MATCH (n) DETACH DELETE n");

    // Create indexes (if not exists)
    try {
      await session.run("CREATE INDEX vendor_id_idx FOR (v:Vendor) ON (v.id)");
      await session.run("CREATE INDEX invoice_id_idx FOR (i:Invoice) ON (i.id)");
      await session.run("CREATE INDEX invoice_status_idx FOR (i:Invoice) ON (i.status)");
    } catch (e) {
      // Indexes may already exist
    }

    // Demo vendors
    const vendors = [
      { id: "vendor-001", name: "Acme Office Supplies", category: "office_supplies", trustScore: 0.92, riskLevel: "LOW" },
      { id: "vendor-002", name: "Tech Solutions Inc", category: "software", trustScore: 0.78, riskLevel: "MEDIUM" },
      { id: "vendor-003", name: "Global Logistics LLC", category: "shipping", trustScore: 0.95, riskLevel: "LOW" },
      { id: "vendor-004", name: "Rapid Parts Co", category: "manufacturing", trustScore: 0.65, riskLevel: "MEDIUM" },
      { id: "vendor-005", name: "Suspicious Vendor LLC", category: "consulting", trustScore: 0.25, riskLevel: "HIGH" },
      { id: "vendor-006", name: "Startup Services", category: "professional_services", trustScore: 0.55, riskLevel: "MEDIUM" },
    ];

    // Create vendors using MERGE
    for (const v of vendors) {
      await session.run(
        `MERGE (v:Vendor {id: $id})
         SET v.name = $name,
             v.category = $category,
             v.trust_score = $trustScore,
             v.risk_level = $riskLevel,
             v.created_at = datetime()`,
        v
      );
      nodes++;
    }

    // Create invoices with relationships
    const invoices = [
      { id: "invoice-001", invoiceNumber: "INV-2024-001", vendorId: "vendor-001", amount: 2450, riskScore: 0.15, riskLevel: "LOW", status: "PENDING" },
      { id: "invoice-002", invoiceNumber: "INV-2024-002", vendorId: "vendor-001", amount: 890, riskScore: 0.10, riskLevel: "LOW", status: "PENDING" },
      { id: "invoice-003", invoiceNumber: "INV-2024-003", vendorId: "vendor-002", amount: 15750, riskScore: 0.52, riskLevel: "MEDIUM", status: "PENDING" },
      { id: "invoice-004", invoiceNumber: "INV-2024-004", vendorId: "vendor-002", amount: 2800, riskScore: 0.28, riskLevel: "LOW", status: "PENDING" },
      { id: "invoice-005", invoiceNumber: "INV-2024-005", vendorId: "vendor-003", amount: 3200, riskScore: 0.12, riskLevel: "LOW", status: "PENDING" },
      { id: "invoice-006", invoiceNumber: "INV-2024-006", vendorId: "vendor-004", amount: 12500, riskScore: 0.68, riskLevel: "HIGH", status: "PENDING" },
      { id: "invoice-007", invoiceNumber: "INV-2024-007", vendorId: "vendor-005", amount: 45000, riskScore: 0.89, riskLevel: "CRITICAL", status: "NEW" },
      { id: "invoice-008", invoiceNumber: "INV-2024-008", vendorId: "vendor-006", amount: 7500, riskScore: 0.45, riskLevel: "MEDIUM", status: "PENDING" },
    ];

    for (const inv of invoices) {
      // Create invoice using MERGE
      await session.run(
        `MERGE (i:Invoice {id: $id})
         SET i.invoice_number = $invoiceNumber,
             i.amount = $amount,
             i.risk_score = $riskScore,
             i.risk_level = $riskLevel,
             i.status = $status,
             i.created_at = datetime()`,
        inv
      );
      nodes++;

      // Delete existing ISSUED relationship if exists
      await session.run(
        `MATCH (v:Vendor {id: $vendorId})-[r:ISSUED]->(i:Invoice {id: $invoiceId})
         DELETE r`,
        { vendorId: inv.vendorId, invoiceId: inv.id }
      );

      // Create new ISSUED relationship
      await session.run(
        `MATCH (v:Vendor {id: $vendorId})
         MATCH (i:Invoice {id: $invoiceId})
         CREATE (v)-[:ISSUED {issued_at: datetime()}]->(i)`,
        { vendorId: inv.vendorId, invoiceId: inv.id }
      );
      relationships++;
    }

    // Create temporal trust history for each vendor
    const now = Date.now();
    const monthMs = 30 * 24 * 60 * 60 * 1000;

    for (const v of vendors) {
      // Delete old trust history
      await session.run(
        `MATCH (v:Vendor {id: $id})-[r:TRUST_HISTORY]->(t:TrustPoint)
         DELETE r, t`,
        { id: v.id }
      );

      for (let i = 0; i < 3; i++) {
        const score = Math.max(0.3, v.trustScore - (i * 0.05) + (Math.random() * 0.1));
        await session.run(
          `MATCH (v:Vendor {id: $id})
           CREATE (v)-[:TRUST_HISTORY {
             from: $from,
             to: $to,
             score: $score
           }]->(:TrustPoint {value: $score})`,
          {
            id: v.id,
            from: now - ((i + 1) * monthMs),
            to: now - (i * monthMs),
            score: score,
          }
        );
        relationships++;
      }
    }

    return { nodes, relationships };
  } finally {
    await session.close();
    await driver.close();
  }
}

/**
 * Get invoice context from Neo4j for agentic decision making
 */
export async function getInvoiceContext(invoiceId: string): Promise<{
  vendor: any;
  invoice: any;
  history: any[];
} | null> {
  const driver = createDriver();
  const session = driver.session();

  try {
    const result = await session.run(
      `MATCH (v:Vendor)-[:ISSUED]->(i:Invoice {id: $invoiceId})
       OPTIONAL MATCH (v)-[:TRUST_HISTORY]->(t:TrustPoint)
       RETURN v, i, collect(t) as trust_history`,
      { invoiceId }
    );

    if (result.records.length === 0) return null;

    const record = result.records[0];
    return {
      vendor: record.get("v").properties,
      invoice: record.get("i").properties,
      history: record.get("trust_history").map((t: any) => t.properties),
    };
  } finally {
    await session.close();
    await driver.close();
  }
}

/**
 * Get Neo4j connection status
 */
export async function getNeo4jStatus(): Promise<{ connected: boolean; nodes: number; relationships: number; error?: string }> {
  const driver = createDriver();
  const session = driver.session();

  try {
    const nodeResult = await session.run("MATCH (n) RETURN count(n) as node_count");
    const relResult = await session.run("MATCH ()-[r]->() RETURN count(r) as rel_count");

    const nodeRecord = nodeResult.records[0];
    const relRecord = relResult.records[0];

    return {
      connected: true,
      nodes: nodeRecord?.get("node_count")?.toNumber() || 0,
      relationships: relRecord?.get("rel_count")?.toNumber() || 0,
    };
  } catch (error: any) {
    return { connected: false, nodes: 0, relationships: 0, error: error.message };
  } finally {
    await session.close();
    await driver.close();
  }
}
