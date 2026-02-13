/**
 * Kafka Integration Test
 *
 * This file tests the Kafka producer with real Kafka brokers.
 *
 * TWO TESTING OPTIONS:
 *
 * 1. UPSTASH KAFKA (Production-ready):
 *    - Get credentials from https://console.upstash.com/kafka
 *    - Set environment variables:
 *      export UPSTASH_KAFKA_REST_URL="https://your-cluster.upstash.io"
 *      export UPSTASH_KAFKA_REST_USERNAME="your-username"
 *      export UPSTASH_KAFKA_REST_PASSWORD="your-password"
 *    - Run: pnpm test -- test/lib/kafka-integration.test.ts
 *
 * 2. REDPANDA LOCAL (Development):
 *    - Start Redpanda: docker run -d --name redpanda --rm -p 8082:8082 -p 9092:9092 redpandadata/redpanda
 *    - Create topics: docker exec redpanda rpk topic create invoice.uploaded invoice.processed
 *    - Test with rpk: docker exec redpanda rpk topic produce invoice.uploaded --key "test"
 *    - Consume: docker exec redpanda rpk topic consume invoice.uploaded --offset 0
 *
 * Note: The Upstash Kafka client uses HTTP and is designed for serverless environments.
 *       Redpanda's HTTP API uses a different format, so for local development,
 *       use rpk (Redpanda CLI) or kafkacat instead.
 */

import { describe, it, expect, beforeAll } from "vitest";
import {
  KafkaProducer,
  resetKafkaProducer,
  type InvoiceUploadedEvent,
  type InvoiceProcessedEvent,
} from "../../src/lib/kafka-producer";

// Test configuration - uses Upstash Kafka via environment variables
const getKafkaConfig = () => ({
  url: process.env.UPSTASH_KAFKA_REST_URL || "mock",
  username: process.env.UPSTASH_KAFKA_REST_USERNAME || "",
  password: process.env.UPSTASH_KAFKA_REST_PASSWORD || "",
  mockMode: !process.env.UPSTASH_KAFKA_REST_URL,
});

describe("Kafka Integration Tests", () => {
  beforeEach(() => {
    resetKafkaProducer();
  });

  describe("Production Upstash Kafka", () => {
    it("should publish invoice.uploaded event with retry logic", async () => {
      const config = getKafkaConfig();

      // Skip if not configured for real Kafka
      if (config.mockMode) {
        console.log("Skipping - set UPSTASH_KAFKA_REST_URL to run integration tests");
        return;
      }

      const producer = new KafkaProducer({
        url: config.url,
        username: config.username,
        password: config.password,
        mockMode: false,
      });

      expect(producer.isConfigured()).toBe(true);

      const event: InvoiceUploadedEvent = {
        invoiceId: `test-inv-${Date.now()}`,
        userId: "test-user-001",
        fileKey: "invoices/test-inv-001.pdf",
        fileName: "test-invoice.pdf",
        mimeType: "application/pdf",
        fileSize: 1024,
        checksum: `abc123${Date.now()}`,
        traceId: "trace-integration-test",
        timestamp: new Date().toISOString(),
        metadata: { source: "integration-test" },
      };

      const result = await producer.publishInvoiceUploaded(event);

      console.log("Publish result:", result);

      expect(result.success).toBe(true);
      expect(result.topic).toBe("invoice.uploaded");
      expect(result.partition).toBeDefined();
      expect(typeof result.offset).toBe("number");
    });

    it("should publish invoice.processed event", async () => {
      const config = getKafkaConfig();

      if (config.mockMode) {
        console.log("Skipping - set UPSTASH_KAFKA_REST_URL to run integration tests");
        return;
      }

      const producer = new KafkaProducer({
        url: config.url,
        username: config.username,
        password: config.password,
        mockMode: false,
      });

      const event: InvoiceProcessedEvent = {
        invoiceId: `test-inv-processed-${Date.now()}`,
        userId: "test-user-001",
        status: "success",
        extractedData: { vendor: "Test Corp", total: 150.0, items: 5 },
        durationMs: 2500,
        traceId: "trace-integration-test-processed",
        timestamp: new Date().toISOString(),
      };

      const result = await producer.publishInvoiceProcessed(event);

      console.log("Processed result:", result);

      expect(result.success).toBe(true);
      expect(result.topic).toBe("invoice.processed");
    });

    it("should handle retry configuration", async () => {
      const config = getKafkaConfig();

      if (config.mockMode) {
        console.log("Skipping - set UPSTASH_KAFKA_REST_URL to run integration tests");
        return;
      }

      const producer = new KafkaProducer({
        url: config.url,
        username: config.username,
        password: config.password,
        mockMode: false,
      });

      const configResult = producer.getRetryConfig();

      expect(configResult.maxRetries).toBe(3);
      expect(configResult.minTimeout).toBe(100);
      expect(configResult.maxTimeout).toBe(5000);
    });
  });

  describe("Mock Mode (Unit Tests)", () => {
    it("should publish successfully in mock mode", async () => {
      const producer = new KafkaProducer({
        url: "mock",
        mockMode: true,
      });

      expect(producer.isConfigured()).toBe(false);

      const event: InvoiceUploadedEvent = {
        invoiceId: "mock-inv-001",
        userId: "test-user-001",
        fileKey: "invoices/mock-inv-001.pdf",
        fileName: "mock-invoice.pdf",
        mimeType: "application/pdf",
        fileSize: 1024,
        checksum: "mock123",
        traceId: "trace-mock-test",
        timestamp: new Date().toISOString(),
      };

      const result = await producer.publishInvoiceUploaded(event);

      expect(result.success).toBe(true);
      expect(result.topic).toBe("invoice.uploaded");
      expect(result.partition).toBe(0);
      expect(result.offset).toBe(1); // Deterministic offset
    });

    it("should publish processed event in mock mode", async () => {
      const producer = new KafkaProducer({ mockMode: true });

      const event: InvoiceProcessedEvent = {
        invoiceId: "mock-inv-002",
        userId: "test-user-001",
        status: "success",
        extractedData: { vendor: "Mock Corp", total: 99.99 },
        durationMs: 100,
        traceId: "trace-mock-processed",
        timestamp: new Date().toISOString(),
      };

      const result = await producer.publishInvoiceProcessed(event);

      expect(result.success).toBe(true);
      expect(result.topic).toBe("invoice.processed");
    });
  });
});

/*
 * REDPANDA LOCAL TESTING COMMANDS:
 *
 * # Start Redpanda
 * docker run -d --name redpanda --rm -p 8082:8082 -p 9092:9092 redpandadata/redpanda
 *
 * # Create topics
 * docker exec redpanda rpk topic create invoice.uploaded invoice.processed
 *
 * # List topics
 * docker exec redpanda rpk topic list
 *
 * # Produce message
 * echo '{"invoiceId":"test","amount":100}' | docker exec -i redpanda rpk topic produce invoice.uploaded
 *
 * # Consume messages
 * docker exec redpanda rpk topic consume invoice.uploaded --num 1
 *
 * # Cleanup
 * docker stop redpanda && docker rm redpanda
 */
