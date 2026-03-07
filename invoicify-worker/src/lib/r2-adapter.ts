/**
 * R2 → Azure Blob Storage adapter.
 *
 * Cloudflare R2 API (used in existing routes):
 *   env.INVOICES_BUCKET.put(key, body)
 *   env.INVOICES_BUCKET.get(key)  → { body: ReadableStream, ...metadata }
 *   env.INVOICES_BUCKET.delete(key)
 *   env.INVOICES_BUCKET.createMultipartUpload(key)
 *
 * This adapter wraps Azure BlobServiceClient to expose the same interface.
 */

import type { BlobServiceClient } from '@azure/storage-blob';

const CONTAINER_NAME = process.env.AZURE_STORAGE_CONTAINER ?? 'invoices';

export class R2Adapter {
  private container;

  constructor(blobService: BlobServiceClient) {
    this.container = blobService.getContainerClient(CONTAINER_NAME);
  }

  async put(
    key: string,
    body: ArrayBuffer | Uint8Array | string | ReadableStream | Blob,
    options?: { httpMetadata?: { contentType?: string } },
  ): Promise<{ key: string }> {
    const blockBlob = this.container.getBlockBlobClient(key);
    let buffer: Buffer;

    if (body instanceof ArrayBuffer) {
      buffer = Buffer.from(body);
    } else if (body instanceof Uint8Array) {
      buffer = Buffer.from(body);
    } else if (typeof body === 'string') {
      buffer = Buffer.from(body, 'utf8');
    } else if (body instanceof Blob) {
      buffer = Buffer.from(await body.arrayBuffer());
    } else {
      // ReadableStream
      const chunks: Uint8Array[] = [];
      const reader = (body as ReadableStream).getReader();
      let done = false;
      while (!done) {
        const { value, done: d } = await reader.read();
        if (value) chunks.push(value);
        done = d;
      }
      buffer = Buffer.concat(chunks);
    }

    await blockBlob.upload(buffer, buffer.length, {
      blobHTTPHeaders: {
        blobContentType: options?.httpMetadata?.contentType ?? 'application/octet-stream',
      },
    });

    return { key };
  }

  async get(key: string): Promise<{ key: string; body: Buffer; arrayBuffer(): Promise<ArrayBuffer> } | null> {
    try {
      const blockBlob = this.container.getBlockBlobClient(key);
      const download = await blockBlob.downloadToBuffer();
      return {
        key,
        body: download,
        async arrayBuffer() { return download.buffer as ArrayBuffer; },
      };
    } catch {
      return null;
    }
  }

  async delete(key: string): Promise<void> {
    const blockBlob = this.container.getBlockBlobClient(key);
    await blockBlob.deleteIfExists();
  }

  async createMultipartUpload(key: string): Promise<{ key: string; uploadId: string }> {
    // Azure blocks are committed in a single uploadBlock call; simulate multipart
    return { key, uploadId: `${key}-${Date.now()}` };
  }
}
