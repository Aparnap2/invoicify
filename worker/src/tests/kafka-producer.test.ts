/**
 * Kafka Producer Tests
 *
 * Tests for the Upstash Kafka producer functionality.
 * Run with: pnpm test -- test/lib/kafka-producer.test.ts
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  KafkaProducer,
  resetKafkaProducer,
  getKafkaProducer,
  type InvoiceUploadedEvent,
  type InvoiceProcessedEvent,
} from "../../src/lib/kafka-producer";

// Mock console methods for testing
const mockConsoleLog = vi.spyOn(console, "log").mockImplementation(() => {});
const mockConsoleError = vi.spyOn(console, "error").mockImplementation(() => {});

describe("KafkaProducer", () => {
  beforeEach(() => {
    resetKafkaProducer();
    mockConsoleLog.mockClear();
    mockConsoleError.mockClear();
  });

  describe("Constructor", () => {
    it("should initialize in mock mode when url is 'mock'", () => {
      const producer = new KafkaProducer({ url: "mock" });
      expect(producer.isConfigured()).toBe(false);
    });

    it("should initialize in real mode when url is provided", () => {
      const producer = new KafkaProducer({
        url: "https://test.upstash.io",
        username: "test",
        password: "test",
      });
      expect(producer.isConfigured()).toBe(true);
    });
  });

  describe("publishInvoiceUploaded", () => {
    it("should publish event successfully in mock mode", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const event: InvoiceUploadedEvent = {
        invoiceId: "inv-001",
        userId: "user-001",
        fileKey: "invoices/2024/01/inv-001.pdf",
        fileName: "invoice-001.pdf",
        mimeType: "application/pdf",
        fileSize: 1024,
        checksum: "abc123",
        traceId: "trace-001",
        timestamp: new Date().toISOString(),
      };

      const result = await producer.publishInvoiceUploaded(event);

      expect(result.success).toBe(true);
      expect(result.topic).toBe("invoice.uploaded");
      expect(result.partition).toBe(0);
      expect(result.offset).toBeGreaterThanOrEqual(0);
    });

    it("should include metadata in event", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const event: InvoiceUploadedEvent = {
        invoiceId: "inv-002",
        userId: "user-001",
        fileKey: "invoices/2024/01/inv-002.pdf",
        fileName: "invoice-002.pdf",
        mimeType: "application/pdf",
        fileSize: 2048,
        checksum: "def456",
        traceId: "trace-002",
        timestamp: new Date().toISOString(),
        metadata: { source: "web", version: "1.0" },
      };

      const result = await producer.publishInvoiceUploaded(event);

      expect(result.success).toBe(true);
      expect(result.topic).toBe("invoice.uploaded");
    });
  });

  describe("publishInvoiceProcessed", () => {
    it("should publish success event in mock mode", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const event: InvoiceProcessedEvent = {
        invoiceId: "inv-001",
        userId: "user-001",
        status: "success",
        extractedData: { vendor: "Acme Corp", total: 150.0 },
        durationMs: 2500,
        traceId: "trace-001",
        timestamp: new Date().toISOString(),
      };

      const result = await producer.publishInvoiceProcessed(event);

      expect(result.success).toBe(true);
      expect(result.topic).toBe("invoice.processed");
      expect(result.partition).toBe(0);
    });

    it("should publish failed event with error in mock mode", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const event: InvoiceProcessedEvent = {
        invoiceId: "inv-002",
        userId: "user-001",
        status: "failed",
        error: "Failed to parse invoice: missing vendor name",
        durationMs: 1200,
        traceId: "trace-002",
        timestamp: new Date().toISOString(),
      };

      const result = await producer.publishInvoiceProcessed(event);

      expect(result.success).toBe(true);
      expect(result.topic).toBe("invoice.processed");
    });
  });

  describe("generic publish method", () => {
    it("should publish to any topic in mock mode", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const result = await producer.publish(
        "custom.topic",
        "key-001",
        { foo: "bar" }
      );

      expect(result.success).toBe(true);
      expect(result.topic).toBe("custom.topic");
      expect(result.partition).toBe(0);
    });
  });

  describe("singleton pattern", () => {
    it("should return same instance on multiple getKafkaProducer calls", () => {
      const producer1 = getKafkaProducer({ url: "mock" });
      const producer2 = getKafkaProducer({ url: "mock" });

      expect(producer1).toBe(producer2);
    });

    it("should reset singleton with resetKafkaProducer", () => {
      const producer1 = getKafkaProducer({ url: "mock" });
      resetKafkaProducer();
      const producer2 = getKafkaProducer({ url: "mock" });

      expect(producer1).not.toBe(producer2);
    });
  });
});

describe("Convenience Functions (Mock Mode)", () => {
  // These tests use the KafkaProducer class directly with mock mode
  // The convenience functions (publishInvoiceUploaded, publishInvoiceProcessed)
  // require environment variables to be set before module load

  describe("Class-based usage", () => {
    beforeEach(() => {
      resetKafkaProducer();
      mockConsoleLog.mockClear();
      mockConsoleError.mockClear();
    });

    it("should publish invoice uploaded using class instance", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const result = await producer.publishInvoiceUploaded({
        invoiceId: "inv-001",
        userId: "user-001",
        fileKey: "invoices/inv-001.pdf",
        fileName: "invoice-001.pdf",
        mimeType: "application/pdf",
        fileSize: 1024,
        checksum: "checksum123",
        traceId: "trace-001",
        timestamp: new Date().toISOString(),
        metadata: { source: "test" },
      });

      expect(result.success).toBe(true);
      expect(result.topic).toBe("invoice.uploaded");
    });

    it("should publish invoice processed using class instance", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const result = await producer.publishInvoiceProcessed({
        invoiceId: "inv-001",
        userId: "user-001",
        status: "success",
        extractedData: { vendor: "Acme", total: 150.0 },
        durationMs: 2000,
        traceId: "trace-001",
        timestamp: new Date().toISOString(),
      });

      expect(result.success).toBe(true);
      expect(result.topic).toBe("invoice.processed");
    });

    it("should publish invoice processed with error status", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const result = await producer.publishInvoiceProcessed({
        invoiceId: "inv-002",
        userId: "user-001",
        status: "failed",
        error: "Failed to parse invoice",
        durationMs: 500,
        traceId: "trace-002",
        timestamp: new Date().toISOString(),
      });

      expect(result.success).toBe(true);
      expect(result.topic).toBe("invoice.processed");
    });
  });
});
