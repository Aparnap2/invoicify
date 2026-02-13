/**
 * Qdrant Integration Test (Real Server)
 *
 * Run with: pnpm test -- test/lib/qdrant-integration.test.ts
 *
 * Requires: Qdrant running at http://localhost:6333
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { QdrantClient, getQdrantClient, resetQdrantClient, type InvoiceDocument } from './qdrant.js';

describe('Qdrant Integration', () => {
  let client: QdrantClient;

  beforeAll(async () => {
    resetQdrantClient();
    client = new QdrantClient({
      url: 'http://localhost:6333',
      collectionName: 'test-invoices',
      mockMode: false,
    });

    // Ensure collection exists
    await client.ensureCollection();
  });

  afterAll(async () => {
    // Cleanup: delete test collection
    try {
      await fetch('http://localhost:6333/collections/test-invoices', { method: 'DELETE' });
    } catch (e) {
      // Ignore cleanup errors
    }
  });

  describe('Collection Management', () => {
    it('should get collection info', async () => {
      const result = await client.getCollection();
      expect(result.exists).toBe(true);
    });
  });

  describe('Upsert Invoices', () => {
    it('should upsert a single invoice', async () => {
      const doc: InvoiceDocument = {
        invoice_id: 'test-inv-001',
        tenant_id: 'test-tenant',
        vendor_name: 'Uber Technologies',
        invoice_number: 'TEST-UBER-001',
        total_amount: 156.50,
        currency: 'USD',
        invoice_date: '2024-01-15',
        status: 'APPROVED',
        extracted_text: 'Uber ride for client meeting downtown. Business purpose: Sales client visit. Department: Sales. Total rides: 5 trips.',
      };

      const result = await client.upsertInvoice(doc);
      expect(result.success).toBe(true);
    });

    it('should upsert multiple invoices', async () => {
      const docs: InvoiceDocument[] = [
        {
          invoice_id: 'test-inv-002',
          tenant_id: 'test-tenant',
          vendor_name: 'AWS',
          invoice_number: 'TEST-AWS-001',
          total_amount: 2450.00,
          currency: 'USD',
          status: 'PENDING',
          extracted_text: 'AWS cloud services. EC2 instances, S3 storage, RDS database. Production environment. Region: us-east-1.',
        },
        {
          invoice_id: 'test-inv-003',
          tenant_id: 'test-tenant',
          vendor_name: 'Slack Technologies',
          invoice_number: 'TEST-SLACK-001',
          total_amount: 850.00,
          currency: 'USD',
          status: 'APPROVED',
          extracted_text: 'Slack Business+ plan. 25 seats. Monthly billing. Team communication and collaboration tool.',
        },
      ];

      const result = await client.upsertInvoices(docs);
      expect(result.success).toBe(true);
      expect(result.points_upserted).toBe(2);
    });
  });

  describe('Semantic Search', () => {
    it('should find Uber receipts', async () => {
      const results = await client.semanticSearch('Uber rides and transportation', {
        limit: 10,
        minScore: 0.3,
      });

      expect(results.some(r => r.vendor_name === 'Uber Technologies')).toBe(true);
    });

    it('should find cloud services invoices', async () => {
      const results = await client.semanticSearch('AWS cloud infrastructure', {
        limit: 10,
        minScore: 0.3,
      });

      expect(results.some(r => r.vendor_name === 'AWS')).toBe(true);
    });

    it('should find communication tools', async () => {
      const results = await client.semanticSearch('team collaboration software', {
        limit: 10,
        minScore: 0.3,
      });

      expect(results.some(r => r.vendor_name === 'Slack Technologies')).toBe(true);
    });

    it('should filter by tenant', async () => {
      const results = await client.semanticSearch('invoices', {
        limit: 10,
        tenantId: 'test-tenant',
        minScore: 0.1,
      });

      expect(results.length).toBeGreaterThan(0);
    });
  });

  describe('Get Invoice', () => {
    it('should retrieve invoice by ID', async () => {
      const invoice = await client.getInvoice('test-inv-001');

      expect(invoice).not.toBeNull();
      expect(invoice?.vendor_name).toBe('Uber Technologies');
      expect(invoice?.total_amount).toBe(156.50);
    });
  });

  describe('Count Invoices', () => {
    it('should count invoices', async () => {
      const count = await client.countInvoices();
      expect(count).toBeGreaterThanOrEqual(3);
    });

    it('should count with tenant filter', async () => {
      const count = await client.countInvoices('test-tenant');
      expect(count).toBeGreaterThanOrEqual(3);
    });
  });

  describe('Delete Invoice', () => {
    it('should delete invoice', async () => {
      const result = await client.deleteInvoice('test-inv-001');
      expect(result).toBe(true);

      // Verify deleted
      const invoice = await client.getInvoice('test-inv-001');
      expect(invoice).toBeNull();
    });
  });
});

describe('Natural Language Search Examples', () => {
  let client: QdrantClient;

  beforeAll(async () => {
    resetQdrantClient();
    client = new QdrantClient({
      url: 'http://localhost:6333',
      collectionName: 'test-search-examples',
      mockMode: false,
    });

    await client.ensureCollection();

    // Insert sample invoices
    const docs: InvoiceDocument[] = [
      {
        invoice_id: 'search-001',
        tenant_id: 'demo',
        vendor_name: 'Uber',
        invoice_number: 'UBER-001',
        total_amount: 245.00,
        currency: 'USD',
        status: 'PENDING',
        extracted_text: 'Uber rides for sales team client visits and business meetings throughout the city.',
      },
      {
        invoice_id: 'search-002',
        tenant_id: 'demo',
        vendor_name: 'Delta Airlines',
        invoice_number: 'DELTA-001',
        total_amount: 1250.00,
        currency: 'USD',
        status: 'APPROVED',
        extracted_text: 'Flight to NYC for quarterly business review meeting with enterprise client.',
      },
      {
        invoice_id: 'search-003',
        tenant_id: 'demo',
        vendor_name: 'Marriott Hotels',
        invoice_number: 'MARRIOTT-001',
        total_amount: 450.00,
        currency: 'USD',
        status: 'APPROVED',
        extracted_text: 'Hotel accommodation for 3 nights during the technology conference.',
      },
    ];

    await client.upsertInvoices(docs);
  });

  afterAll(async () => {
    try {
      await fetch('http://localhost:6333/collections/test-search-examples', { method: 'DELETE' });
    } catch (e) {}
  });

  it('should answer "Show me high value invoices"', async () => {
    const results = await client.semanticSearch('high value expensive invoices over 500 dollars', {
      limit: 10,
      minScore: 0.3,
    });

    expect(results.length).toBeGreaterThan(0);
    // Should find Delta Airlines ($1250)
    expect(results.some(r => r.total_amount > 500)).toBe(true);
  });

  it('should answer "Find travel expenses"', async () => {
    const results = await client.semanticSearch('travel expenses flights hotels transportation', {
      limit: 10,
      minScore: 0.3,
    });

    expect(results.length).toBeGreaterThan(0);
    // Should find Delta and Marriott
    const vendors = results.map(r => r.vendor_name);
    expect(vendors.some(v => v.includes('Delta') || v.includes('Marriott') || v.includes('Uber'))).toBe(true);
  });

  it('should answer "What invoices are pending?"', async () => {
    const results = await client.semanticSearch('pending payment approval needed waiting', {
      limit: 10,
      tenantId: 'demo',
      minScore: 0.3,
    });

    // Should find Uber (pending)
    expect(results.some(r => r.status === 'PENDING')).toBe(true);
  });
});
