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

/** Parsed XAI (explainability) file structure */
export interface XaiData {
  raw: Record<string, unknown>;
  isValid: boolean;
}

/** Combined ML context for Trinity analysis */
export interface ParsedMLContext {
  datadrift: DatadriftData | null;
  observability: ObservabilityData | null;
  xai: XaiData | null;
  /** True when all 3 required files (datadrift, quality/observability, xai) are present */
  hasAllThree: boolean;
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
 * Attempts to parse a file as observability/quality JSON.
 * Heuristics: expect_column_* (Great Expectations) or observability keys.
 */
function parseObservabilityFile(content: string): ObservabilityData {
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>;
    const hasObsKeys =
      typeof parsed === "object" &&
      parsed !== null &&
      (Object.keys(parsed).some((k) =>
        /expect_column|observability|quality/i.test(k)
      ) ||
        Object.keys(parsed).some((k) =>
          /metric|latency|error|model|performance/i.test(k)
        ));
    return { raw: parsed, isValid: !!hasObsKeys };
  } catch {
    return { raw: {}, isValid: false };
  }
}

/**
 * Attempts to parse a file as XAI (explainability) JSON.
 * Heuristics: performanceMetrics, confusionMatrix, featureImportance, shapGlobal.
 */
function parseXaiFile(content: string): XaiData {
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>;
    const hasXaiKeys =
      typeof parsed === "object" &&
      parsed !== null &&
      Object.keys(parsed).some((k) =>
        /performanceMetrics|confusionMatrix|featureImportance|shapGlobal|rocPlot|prPlot/i.test(k)
      );
    return { raw: parsed, isValid: !!hasXaiKeys };
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
  let xai: XaiData | null = null;

  for (const { name, content } of files) {
    const lower = name.toLowerCase();
    if (lower.includes("drift") || lower.includes("datadrift")) {
      datadrift = parseDatadriftFile(content);
    } else if (
      lower.includes("observability") ||
      lower.includes("quality") ||
      lower.includes("qualitycheck")
    ) {
      observability = parseObservabilityFile(content);
    } else if (lower.includes("xai") || lower.includes("explain")) {
      xai = parseXaiFile(content);
    } else {
      const d = parseDatadriftFile(content);
      const o = parseObservabilityFile(content);
      const x = parseXaiFile(content);
      if (d.isValid && !datadrift) datadrift = d;
      if (o.isValid && !observability) observability = o;
      if (x.isValid && !xai) xai = x;
    }
  }

  return {
    datadrift,
    observability,
    xai,
    hasAllThree: !!(datadrift?.isValid && observability?.isValid && xai?.isValid),
  };
}
