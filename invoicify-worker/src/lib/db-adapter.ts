/**
 * D1 → PostgreSQL adapter.
 *
 * Cloudflare D1 uses a SQLite-style API:
 *   env.DB.prepare(sql).bind(...args).all()
 *   env.DB.prepare(sql).bind(...args).run()
 *   env.DB.prepare(sql).bind(...args).first()
 *
 * This adapter wraps a pg.Pool to expose the same interface so existing
 * route code requires ZERO changes.
 *
 * Usage in routes (unchanged):
 *   const result = await env.DB.prepare('SELECT * FROM invoices WHERE id = ?1').bind(id).first();
 */

import type { Pool, PoolClient } from 'pg';

class D1Statement {
  private sql: string;
  private args: unknown[];
  private pool: Pool;

  constructor(pool: Pool, sql: string) {
    // D1 uses ?1, ?2 positional params; pg uses $1, $2
    this.sql = sql.replace(/\?(\d+)/g, '\$$1');
    this.pool = pool;
    this.args = [];
  }

  bind(...args: unknown[]): D1Statement {
    this.args = args;
    return this;
  }

  async all<T = Record<string, unknown>>(): Promise<{ results: T[] }> {
    const { rows } = await this.pool.query(this.sql, this.args as any[]);
    return { results: rows as T[] };
  }

  async run(): Promise<{ success: boolean; meta: { changes: number } }> {
    const result = await this.pool.query(this.sql, this.args as any[]);
    return { success: true, meta: { changes: result.rowCount ?? 0 } };
  }

  async first<T = Record<string, unknown>>(): Promise<T | null> {
    const { rows } = await this.pool.query(this.sql, this.args as any[]);
    return (rows[0] as T) ?? null;
  }
}

export class D1Adapter {
  constructor(private pool: Pool) {}

  prepare(sql: string): D1Statement {
    return new D1Statement(this.pool, sql);
  }

  async batch<T>(statements: D1Statement[]): Promise<T[]> {
    const client: PoolClient = await this.pool.connect();
    try {
      await client.query('BEGIN');
      const results: T[] = [];
      for (const stmt of statements) {
        const r = await (stmt as any).all();
        results.push(r);
      }
      await client.query('COMMIT');
      return results;
    } catch (e) {
      await client.query('ROLLBACK');
      throw e;
    } finally {
      client.release();
    }
  }
}
