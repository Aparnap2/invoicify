/**
 * Structured Logging for Cloudflare Workers
 *
 * Provides JSON-structured logs that work with Cloudflare Logs
 * and external observability platforms (Datadog, Honeycomb, etc.)
 *
 * Log Levels: DEBUG, INFO, WARN, ERROR
 */

export type LogLevel = "DEBUG" | "INFO" | "WARN" | "ERROR";

export interface LogContext {
  traceId?: string;
  invoiceId?: string;
  vendorId?: string;
  userId?: string;
  endpoint?: string;
  action?: string;
  [key: string]: unknown;
}

interface LogEntry {
  level: LogLevel;
  message: string;
  timestamp: string;
  environment: string;
  context: LogContext;
  data?: Record<string, unknown>;
  error?: {
    name: string;
    message: string;
    stack?: string;
  };
}

// Get environment from global or default to "development"
const ENVIRONMENT = (globalThis as any).ENVIRONMENT || "development";

/**
 * Format log entry as JSON string
 */
function formatLogEntry(entry: LogEntry): string {
  return JSON.stringify(entry);
}

/**
 * Get caller location for better log attribution
 */
function getCallerLocation(): string {
  // In Cloudflare Workers, we can't easily get stack traces
  // This is a simplified version that works in V8
  try {
    const stack = new Error().stack?.split("\n") || [];
    // Skip Error, formatLogEntry, and logger functions
    const caller = stack[4] || "unknown";
    return caller.trim();
  } catch {
    return "unknown";
  }
}

/**
 * Core logger function
 */
function log(
  level: LogLevel,
  message: string,
  context: LogContext = {},
  data?: Record<string, unknown>,
  error?: Error
): void {
  const entry: LogEntry = {
    level,
    message,
    timestamp: new Date().toISOString(),
    environment: ENVIRONMENT,
    context: {
      ...context,
      caller: getCallerLocation(),
    },
    data,
  };

  if (error) {
    entry.error = {
      name: error.name || "Error",
      message: error.message,
      stack: error.stack,
    };
  }

  // Output as JSON for structured logging
  console.log(formatLogEntry(entry));

  // In production, you could also send to external observability:
  // - Datadog (fetch to localhost:8126 or agent)
  // - Honeycomb (fetch to api.honeycomb.io)
  // - Cloudflare Logpush (automatic with logpush = true in wrangler.toml)
}

/**
 * Create a child logger with pre-filled context
 */
export function createChildLogger(context: LogContext): Logger {
  return new Logger(context);
}

/**
 * Logger class with methods for each log level
 */
export class Logger {
  private context: LogContext;

  constructor(context: LogContext = {}) {
    this.context = context;
  }

  debug(message: string, data?: Record<string, unknown>, error?: Error): void {
    log("DEBUG", message, this.context, data, error);
  }

  info(message: string, data?: Record<string, unknown>, error?: Error): void {
    log("INFO", message, this.context, data, error);
  }

  warn(message: string, data?: Record<string, unknown>, error?: Error): void {
    log("WARN", message, this.context, data, error);
  }

  error(message: string, data?: Record<string, unknown>, error?: Error): void {
    log("ERROR", message, this.context, data, error);
  }

  /**
   * Log a workflow event
   */
  workflow(action: string, invoiceId: string, traceId: string, data?: Record<string, unknown>): void {
    log("INFO", `Workflow: ${action}`, {
      ...this.context,
      invoiceId,
      traceId,
      action,
    }, data);
  }

  /**
   * Log an HTTP request
   */
  request(method: string, path: string, status: number, duration: number, context?: LogContext): void {
    const level = status >= 500 ? "WARN" : status >= 400 ? "WARN" : "INFO";
    log(level, `${method} ${path} ${status}`, {
      ...this.context,
      ...context,
      method,
      path,
      status,
      duration_ms: duration,
    });
  }

  /**
   * Log a risk assessment
   */
  riskAssessment(invoiceId: string, vendorId: string, score: number, level: string): void {
    log("INFO", `Risk assessment: ${level}`, {
      ...this.context,
      invoiceId,
      vendorId,
      riskScore: score,
      riskLevel: level,
    });
  }

  /**
   * Log a HITL event
   */
  hitl(action: string, invoiceId: string, approver?: string): void {
    log("INFO", `HITL ${action}`, {
      ...this.context,
      invoiceId,
      approver,
      action,
    });
  }

  /**
   * Log an error with full context
   */
  errorWithContext(
    message: string,
    error: Error,
    context: Record<string, unknown>
  ): void {
    log("ERROR", message, this.context, context, error);
  }
}

// ============================================================================
// Default logger instance
// ============================================================================

export const logger = new Logger();

// ============================================================================
// Convenience exports
// ============================================================================

export function debug(message: string, data?: Record<string, unknown>): void {
  logger.debug(message, data);
}

export function info(message: string, data?: Record<string, unknown>): void {
  logger.info(message, data);
}

export function warn(message: string, data?: Record<string, unknown>): void {
  logger.warn(message, data);
}

export function error(message: string, error?: Error, data?: Record<string, unknown>): void {
  logger.error(message, data, error);
}
