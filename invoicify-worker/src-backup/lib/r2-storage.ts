import type { Env, R2Bucket, R2Object } from "../db";

/**
 * File metadata for uploaded invoices
 */
export interface InvoiceFileMetadata {
  invoiceId: string;
  fileName: string;
  mimeType: string;
  size: number;
  uploadedAt: string;
  checksum: string;
}

/**
 * Upload result from R2
 */
export interface UploadResult {
  success: boolean;
  url?: string;
  key?: string;
  error?: string;
  metadata?: InvoiceFileMetadata;
}

/**
 * R2 list result
 */
export interface R2ListResult {
  objects: Array<{ key: string; size: number }>;
}

/**
 * Generate a unique storage key for an invoice file
 */
export function generateStorageKey(
  invoiceId: string,
  fileName: string,
  mimeType: string
): string {
  const timestamp = Date.now();
  const extension = getFileExtension(fileName, mimeType);
  return `invoices/${invoiceId}/${timestamp}.${extension}`;
}

/**
 * Get file extension from filename or mime type
 */
function getFileExtension(
  fileName: string,
  mimeType: string
): string {
  // Try to get extension from filename first
  const nameParts = fileName.split(".");
  if (nameParts.length > 1) {
    return nameParts[nameParts.length - 1].toLowerCase();
  }

  // Fall back to mime type
  const mimeToExt: Record<string, string> = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "application/pdf": "pdf",
    "image/tiff": "tiff",
  };

  return mimeToExt[mimeType] || "bin";
}

/**
 * Upload a file to R2
 */
export async function uploadToR2(
  env: Env,
  key: string,
  body: ArrayBuffer,
  mimeType: string,
  metadata?: Record<string, string>
): Promise<UploadResult> {
  try {
    await env.INVOICE_BUCKET.put(key, body, {
      httpMetadata: {
        contentType: mimeType,
        ...metadata,
      },
    });

    const url = `https://${env.INVOICE_BUCKET}.r2.dev/${key}`;

    return {
      success: true,
      url,
      key,
    };
  } catch (error) {
    return {
      success: false,
      error: `R2 upload failed: ${error}`,
    };
  }
}

/**
 * Upload base64-encoded image to R2
 */
export async function uploadBase64ToR2(
  env: Env,
  key: string,
  base64Data: string,
  mimeType: string,
  metadata?: Record<string, string>
): Promise<UploadResult> {
  try {
    const binary = Buffer.from(base64Data, "base64");
    // Convert Buffer to ArrayBuffer
    const arrayBuffer = binary.buffer.slice(
      binary.byteOffset,
      binary.byteOffset + binary.byteLength
    );
    return await uploadToR2(env, key, arrayBuffer, mimeType, metadata);
  } catch (error) {
    return {
      success: false,
      error: `Base64 upload failed: ${error}`,
    };
  }
}

/**
 * Download a file from R2
 */
export async function downloadFromR2(
  env: Env,
  key: string
): Promise<{ data: ArrayBuffer | null; object: R2Object | null; error?: string }> {
  try {
    const object = await env.INVOICE_BUCKET.get(key);

    if (!object) {
      return { data: null, object: null, error: "File not found" };
    }

    const data = await object.arrayBuffer();
    return { data, object };
  } catch (error) {
    return { data: null, object: null, error: `R2 download failed: ${error}` };
  }
}

/**
 * Get public URL for R2 object
 */
export function getPublicUrl(key: string, bucketName: string): string {
  return `https://${bucketName}.r2.dev/${key}`;
}

/**
 * Delete a file from R2
 */
export async function deleteFromR2(
  env: Env,
  key: string
): Promise<{ success: boolean; error?: string }> {
  try {
    await env.INVOICE_BUCKET.delete(key);
    return { success: true };
  } catch (error) {
    return {
      success: false,
      error: `R2 delete failed: ${error}`,
    };
  }
}

/**
 * Check if a file exists in R2
 */
export async function fileExistsInR2(
  env: Env,
  key: string
): Promise<boolean> {
  try {
    const object = await env.INVOICE_BUCKET.get(key);
    return object !== null;
  } catch {
    return false;
  }
}

/**
 * Generate checksum for file integrity verification
 */
export async function generateFileChecksum(
  data: ArrayBuffer
): Promise<string> {
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Copy a file within R2
 */
export async function copyFileInR2(
  env: Env,
  sourceKey: string,
  destinationKey: string
): Promise<{ success: boolean; error?: string }> {
  try {
    const source = await env.INVOICE_BUCKET.get(sourceKey);

    if (!source) {
      return { success: false, error: "Source file not found" };
    }

    const data = await source.arrayBuffer();
    const mimeType = source.httpMetadata?.contentType || "application/octet-stream";

    await env.INVOICE_BUCKET.put(destinationKey, data, {
      httpMetadata: { contentType: mimeType },
    });

    return { success: true };
  } catch (error) {
    return { success: false, error: `R2 copy failed: ${error}` };
  }
}
