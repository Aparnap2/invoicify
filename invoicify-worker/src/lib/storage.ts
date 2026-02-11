/**
 * R2 Storage Utilities
 * 
 * Handles uploading and downloading invoices and processed results
 */

export function generateRawKey(traceId: string): string {
  const date = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
  return `raw/${date}/${traceId}.pdf`;
}

export function generateProcessedKey(traceId: string): string {
  const date = new Date().toISOString().split('T')[0];
  return `processed/${date}/${traceId}.json`;
}

export interface UploadResult {
  r2Key: string;
  size: number;
  etag: string;
}

export async function uploadInvoicePDF(
  bucket: R2Bucket,
  traceId: string,
  data: ArrayBuffer,
  contentType: string = 'application/pdf'
): Promise<UploadResult> {
  const r2Key = generateRawKey(traceId);
  
  const result = await bucket.put(r2Key, data, {
    httpMetadata: { contentType },
    customMetadata: {
      traceId,
      uploadedAt: new Date().toISOString()
    }
  });
  
  if (!result) {
    throw new Error(`Failed to upload PDF to R2: ${r2Key}`);
  }
  
  return {
    r2Key,
    size: data.byteLength,
    etag: result.etag
  };
}

export async function downloadInvoicePDF(
  bucket: R2Bucket,
  r2Key: string
): Promise<ArrayBuffer | null> {
  const object = await bucket.get(r2Key);
  
  if (!object) {
    return null;
  }
  
  return await object.arrayBuffer();
}

export async function storeProcessedResult(
  bucket: R2Bucket,
  traceId: string,
  data: object
): Promise<UploadResult> {
  const r2Key = generateProcessedKey(traceId);
  const jsonData = JSON.stringify(data, null, 2);
  const encoder = new TextEncoder();
  const buffer = encoder.encode(jsonData);
  
  const result = await bucket.put(r2Key, buffer, {
    httpMetadata: { contentType: 'application/json' },
    customMetadata: {
      traceId,
      processedAt: new Date().toISOString()
    }
  });
  
  if (!result) {
    throw new Error(`Failed to store processed result: ${r2Key}`);
  }
  
  return {
    r2Key,
    size: buffer.byteLength,
    etag: result.etag
  };
}

export async function getProcessedResult(
  bucket: R2Bucket,
  r2Key: string
): Promise<object | null> {
  const object = await bucket.get(r2Key);
  
  if (!object) {
    return null;
  }
  
  const text = await object.text();
  
  try {
    return JSON.parse(text);
  } catch (error) {
    console.error(`Failed to parse JSON from ${r2Key}:`, error);
    return null;
  }
}

export async function deleteInvoiceFiles(
  bucket: R2Bucket,
  traceId: string
): Promise<void> {
  const rawKey = generateRawKey(traceId);
  const processedKey = generateProcessedKey(traceId);
  
  await Promise.all([
    bucket.delete(rawKey),
    bucket.delete(processedKey)
  ]);
}

export async function listInvoicesByDate(
  bucket: R2Bucket,
  date: string // YYYY-MM-DD
): Promise<Array<{ key: string; size: number; uploadedAt: string }>> {
  const prefix = `raw/${date}/`;
  const objects = await bucket.list({ prefix });
  
  return objects.objects.map(obj => ({
    key: obj.key,
    size: obj.size,
    uploadedAt: obj.uploaded?.toISOString() || ''
  }));
}
