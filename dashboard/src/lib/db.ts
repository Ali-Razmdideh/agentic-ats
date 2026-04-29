// Single shared `pg` Pool. Module-level singleton survives Next.js HMR.
import { Pool, type PoolClient } from "pg";

const globalForPool = globalThis as unknown as { __atsPgPool?: Pool };

export const pool: Pool =
  globalForPool.__atsPgPool ??
  new Pool({
    connectionString:
      process.env.DATABASE_URL ?? "postgresql://ats:ats@localhost:5432/ats",
    max: 10,
  });

if (process.env.NODE_ENV !== "production") {
  globalForPool.__atsPgPool = pool;
}

/** Run a callback inside a single connection (useful for transactions). */
export async function withClient<T>(
  fn: (c: PoolClient) => Promise<T>,
): Promise<T> {
  const client = await pool.connect();
  try {
    return await fn(client);
  } finally {
    client.release();
  }
}

/** Run a callback inside a BEGIN/COMMIT, rolling back on throw. */
export async function withTx<T>(fn: (c: PoolClient) => Promise<T>): Promise<T> {
  return withClient(async (c) => {
    await c.query("BEGIN");
    try {
      const r = await fn(c);
      await c.query("COMMIT");
      return r;
    } catch (e) {
      await c.query("ROLLBACK");
      throw e;
    }
  });
}
