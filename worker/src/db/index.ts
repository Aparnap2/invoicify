import { drizzle } from "drizzle-orm/d1";
import type { D1Database } from "@cloudflare/workers-types";
import * as schema from "./schema";

export type Env = {
  DB: D1Database;
  AI: Ai;
  INVOICE_BUCKET: R2Bucket;
  ASSETS: any;
  // API Keys from wrangler.toml secrets/.env
  STRIPE_TEST_KEY: string;
  QUICKBOOKS_CLIENT_ID: string;
  QUICKBOOKS_CLIENT_SECRET: string;
  QUICKBOOKS_REFRESH_TOKEN: string;
  QUICKBOOKS_REALM_ID: string;
};

export interface Ai {
  run(model: string, inputs: any): Promise<any>;
}

export interface R2Bucket {
  put(key: string, value: ArrayBuffer, options?: { httpMetadata?: { contentType?: string } }): Promise<R2Object>;
  get(key: string): Promise<R2Object | null>;
  delete(key: string): Promise<void>;
}

export interface R2Object {
  key: string;
  size: number;
  httpMetadata?: { contentType?: string };
  arrayBuffer(): Promise<ArrayBuffer>;
  text(): Promise<string>;
}

export function getDb(env: Env) {
  return drizzle(env.DB, { schema });
}

export { schema };
