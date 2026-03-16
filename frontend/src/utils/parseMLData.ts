/**
 * parseMLData.ts — Trinity ML Data Parser
 * Parses datadrift response and observability JSON files from Trinity platform.
 * Structure will be finalized once sample JSON schemas are provided.
 */

/** Parsed datadrift response structure (placeholder - refine with sample) */
export interface DatadriftData {
  /** Raw parsed JSON - structure TBD from Trinity sample */
  raw: Record<string, unknown>;
  /** Whether the file appears to be valid datadrift format */
  isValid: boolean;
}

/** Parsed observability file structure (placeholder - refine with sample) */
export interface ObservabilityData {
  /** Raw parsed JSON - structure TBD from Trinity sample */
  raw: Record<string, unknown>;
  /** Whether the file appears to be valid observability format */
  isValid: boolean;
}

/** Combined ML context for Trinity analysis */
export interface ParsedMLContext {
  datadrift: DatadriftData | null;
  observability: ObservabilityData | null;
}

/**
 * Attempts to parse a file as datadrift response JSON.
 * Heuristics: look for common drift-related keys (drift, metrics, features, etc.)
 */
function parseDatadriftFile(content: string): DatadriftData {
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>;
    // Placeholder validation - refine when sample structure is provided
    const hasDriftKeys =
      typeof parsed === "object" &&
      (parsed !== null) &&
      (Object.keys(parsed).some((k) =>
        /drift|metric|feature|distribution/i.test(k)
      ) ||
        Array.isArray(parsed) ||
        "data" in parsed);
    return {
      raw: parsed,
      isValid: hasDriftKeys,
    };
  } catch {
    return { raw: {}, isValid: false };
  }
}

/**
 * Attempts to parse a file as observability JSON.
 * Heuristics: look for observability-related keys (metrics, latency, errors, etc.)
 */
function parseObservabilityFile(content: string): ObservabilityData {
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>;
    // Placeholder validation - refine when sample structure is provided
    const hasObsKeys =
      typeof parsed === "object" &&
      (parsed !== null) &&
      Object.keys(parsed).some((k) =>
        /observability|metric|latency|error|model|performance/i.test(k)
      );
    return {
      raw: parsed,
      isValid: hasObsKeys,
    };
  } catch {
    return { raw: {}, isValid: false };
  }
}

/**
 * Parses ML datasource files from Trinity.
 * Accepts file contents and optional filenames to infer type.
 *
 * @param files - Array of { name, content } from uploaded JSON files
 * @returns ParsedMLContext with datadrift and observability data
 */
export function parseMLData(
  files: Array<{ name: string; content: string }>
): ParsedMLContext {
  let datadrift: DatadriftData | null = null;
  let observability: ObservabilityData | null = null;

  for (const { name, content } of files) {
    const lower = name.toLowerCase();
    // Infer type from filename if possible
    if (lower.includes("drift") || lower.includes("datadrift")) {
      datadrift = parseDatadriftFile(content);
    } else if (
      lower.includes("observability") ||
      lower.includes("obs") ||
      lower.includes("trinity")
    ) {
      observability = parseObservabilityFile(content);
    } else {
      // Try both parsers and use the one that validates
      const d = parseDatadriftFile(content);
      const o = parseObservabilityFile(content);
      if (d.isValid && !datadrift) datadrift = d;
      if (o.isValid && !observability) observability = o;
    }
  }

  return { datadrift, observability };
}
