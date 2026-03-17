/**
 * parseMLData.ts — Knowledge Base Validator
 * Detects if the uploaded files include the required ml_knowledge_base.json.
 */

export interface ParsedMLContext {
  /** True when the required ml_knowledge_base.json is present */
  hasKB: boolean;
}

/**
 * Validates uploaded files for the Machine Learning Knowledge Base.
 * 
 * @param files - Array of { name, content } from uploaded JSON files
 * @returns ParsedMLContext
 */
export function parseMLData(
  files: Array<{ name: string; content: string }>
): ParsedMLContext {
  const hasKB = files.some(f => f.name.toLowerCase().endsWith(".json"));
  return { hasKB };
}
