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

// Mock console methods for testing (logger uses console.log internally)
const mockConsoleLog = vi.spyOn(console, "log").mockImplementation(() => {});
const mockConsoleError = vi.spyOn(console, "error").mockImplementation(() => {});

describe("KafkaProducer", () => {
  beforeEach(() => {
    resetKafkaProducer();
    mockConsoleLog.mockClear();
    mockConsoleError.mockClear();
    vi.clearAllMocks();
  });

  describe("Constructor", () => {
    it("should initialize in mock mode when url is 'mock' (backwards compatibility)", () => {
      const producer = new KafkaProducer({ url: "mock" });
      expect(producer.isConfigured()).toBe(false);
    });

    it("should initialize in mock mode with explicit mockMode flag", () => {
      const producer = new KafkaProducer({ mockMode: true });
      expect(producer.isConfigured()).toBe(false);
    });

    it("should initialize in mock mode via environment variable", () => {
      vi.stubEnv("KAFKA_MOCK_MODE", "true");
      const producer = new KafkaProducer({
        url: "https://test.upstash.io",
        username: "test",
        password: "test",
      });
      expect(producer.isConfigured()).toBe(false);
      vi.unstubAllEnvs();
    });

    it("should initialize in real mode when credentials are provided", () => {
      const producer = new KafkaProducer({
        url: "https://test.upstash.io",
        username: "test",
        password: "test",
      });
      expect(producer.isConfigured()).toBe(true);
    });

    it("should throw error when URL is missing", () => {
      expect(() => {
        new KafkaProducer({
          url: "",
          username: "test",
          password: "test",
        });
      }).toThrow("Missing environment variables");
    });

    it("should throw error when username is missing", () => {
      expect(() => {
        new KafkaProducer({
          url: "https://test.upstash.io",
          username: "",
          password: "test",
        });
      }).toThrow("Missing environment variables");
    });

    it("should throw error when password is missing", () => {
      expect(() => {
        new KafkaProducer({
          url: "https://test.upstash.io",
          username: "test",
          password: "",
        });
      }).toThrow("Missing environment variables");
    });

    it("should throw error when all credentials are missing", () => {
      expect(() => {
        new KafkaProducer({
          url: "",
          username: "",
          password: "",
        });
      }).toThrow("UPSTASH_KAFKA_REST_URL, UPSTASH_KAFKA_REST_USERNAME, UPSTASH_KAFKA_REST_PASSWORD");
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
      expect(result.offset).toBe(1); // Deterministic offset
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
      expect(result.offset).toBe(1); // Deterministic offset
    });

    it("should have deterministic offset across calls", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const event1: InvoiceUploadedEvent = {
        invoiceId: "inv-001",
        userId: "user-001",
        fileKey: "invoices/inv-001.pdf",
        fileName: "invoice-001.pdf",
        mimeType: "application/pdf",
        fileSize: 1024,
        checksum: "checksum1",
        traceId: "trace-001",
        timestamp: new Date().toISOString(),
      };

      const event2: InvoiceUploadedEvent = {
        invoiceId: "inv-002",
        userId: "user-001",
        fileKey: "invoices/inv-002.pdf",
        fileName: "invoice-002.pdf",
        mimeType: "application/pdf",
        fileSize: 2048,
        checksum: "checksum2",
        traceId: "trace-002",
        timestamp: new Date().toISOString(),
      };

      const result1 = await producer.publishInvoiceUploaded(event1);
      const result2 = await producer.publishInvoiceUploaded(event2);

      // Both should have the same deterministic offset (1)
      expect(result1.offset).toBe(1);
      expect(result2.offset).toBe(1);
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
      expect(result.offset).toBe(1); // Deterministic offset
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
      expect(result.offset).toBe(1); // Deterministic offset
    });
  });

  describe("Dead Letter Queue (DLQ)", () => {
    it("should publish to DLQ topic in mock mode", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const result = await producer.publishToDLQ(
        "invoice.uploaded",
        { invoiceId: "inv-001", traceId: "trace-001" },
        "Test error"
      );

      expect(result.success).toBe(true);
      expect(result.topic).toBe("invoice.uploaded.dlq");
      expect(result.partition).toBe(0);
      expect(result.offset).toBe(-1); // Special offset for DLQ
    });

    it("should append .dlq to topic name", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const result = await producer.publishToDLQ(
        "custom.topic",
        { invoiceId: "inv-001" },
        "Error"
      );

      expect(result.topic).toBe("custom.topic.dlq");
    });

    it("should not append .dlq if already present", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const result = await producer.publishToDLQ(
        "invoice.uploaded.dlq",
        { invoiceId: "inv-001" },
        "Error"
      );

      expect(result.topic).toBe("invoice.uploaded.dlq");
    });
  });

  describe("generic publish method", () => {
    it("should publish to any topic in mock mode", async () => {
      const producer = new KafkaProducer({ url: "mock" });

      const result = await producer.publish("custom.topic", "key-001", {
        foo: "bar",
      });

      expect(result.success).toBe(true);
      expect(result.topic).toBe("custom.topic");
      expect(result.partition).toBe(0);
      expect(result.offset).toBe(1); // Deterministic offset
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
