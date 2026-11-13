/** The subset of Bun's Postgres client this server calls. See bun.com/docs/runtime/sql. */
interface SqlCallable {
  (strings: TemplateStringsArray, ...values: unknown[]): Promise<Record<string, unknown>[]>;
  json(value: unknown): unknown;
  begin<T>(run: (tx: SqlCallable) => Promise<T>): Promise<T>;
}

interface SqlConstructor {
  new (url: string): SqlCallable;
}

declare module "bun" {
  export const SQL: SqlConstructor;
}
