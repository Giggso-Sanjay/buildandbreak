"""
AI Deployment Safety Engine — MCP Server
==========================================
Exposes 7 ML risk intelligence tools to the nanobot agent via MCP protocol.
Replaces the old mcp_math_server.py.
"""

import asyncio
import json
import sys
from typing import Any, Dict, List

from mcp.server.models import InitializationOptions
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

from app.tools_ml import (
    get_model_performance,
    get_drift_report,
    get_bias_report,
    get_data_quality_report,
    get_feature_importance,
    assess_deployment_risk,
    explain_metric,
    orchestrate_query,
)


server = Server("ml-risk-engine")


@server.list_tools()
async def list_tools() -> List[Tool]:
    """Expose ML risk intelligence tools to the nanobot agent."""
    return [
        Tool(
            name="get_model_performance",
            description=(
                "Get current model performance metrics (accuracy, precision, recall, F1, AUC) "
                "compared against reference/baseline metrics. Shows how the model is performing "
                "and whether it has degraded."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_drift_report",
            description=(
                "Check for data drift or target drift in the model's production data. "
                "Data drift means feature distributions have changed; target drift means "
                "the prediction target distribution has shifted."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "drift_type": {
                        "type": "string",
                        "description": "Type of drift to check: 'data' for feature drift, 'target' for target drift.",
                        "enum": ["data", "target"],
                    },
                },
                "required": ["drift_type"],
            },
        ),
        Tool(
            name="get_bias_report",
            description=(
                "Get the fairness and bias analysis report. Shows which fairness metrics "
                "flag bias, which protected attributes are affected, and whether the model "
                "treats privileged and unprivileged groups equitably."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_data_quality_report",
            description=(
                "Get data quality assessment including quality check pass/fail rates, "
                "data freshness status, data integrity, and dataset schema information."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_feature_importance",
            description=(
                "Get feature importance rankings showing which features most influence "
                "the model's predictions. Supports SHAP values or permutation importance."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "Method for feature importance: 'shap' for SHAP values, 'importance' for permutation importance.",
                        "enum": ["shap", "importance"],
                    },
                },
                "required": ["method"],
            },
        ),
        Tool(
            name="assess_deployment_risk",
            description=(
                "THE KEY TOOL — Performs a comprehensive deployment risk assessment. "
                "Computes a risk score (0-1) across 6 dimensions (operational errors, "
                "model strength, calibration, bias, drift, data quality), makes a "
                "deployment decision (SAFE/CAUTION/DO_NOT_DEPLOY), lists primary risks, "
                "and generates recommended actions. Use this when asked about deployment "
                "safety, risk assessment, or whether the model should be deployed."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "description": "Which model pipeline to use: 'classic' for traditional ML models, 'llm' for LLM-based models evaluated via firewall + observability JSONs.",
                        "enum": ["classic", "llm"],
                    },
                    "model_id": {
                        "type": "string",
                        "description": "Optional model identifier or version (for reporting).",
                    },
                    "model_type": {
                        "type": "string",
                        "description": "Optional model type label to include in the response (e.g., 'classic', 'llm').",
                    },
                    "firewall_path": {
                        "type": "string",
                        "description": "Optional path to the LLM firewall JSON file. If omitted in LLM mode, a default mlinsight path is used.",
                    },
                    "observability_path": {
                        "type": "string",
                        "description": "Optional path to the LLM observability JSON file. If omitted in LLM mode, a default mlinsight path is used.",
                    },
                    "performance_path": {
                        "type": "string",
                        "description": "Optional path to the LLM performance JSON file. If omitted in LLM mode, a default mlinsight path is used.",
                    },
                    "clarity_path": {
                        "type": "string",
                        "description": "Optional path to the LLM clarity JSON file. If omitted in LLM mode, a default mlinsight path is used.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="explain_metric",
            description=(
                "Explain any ML metric in plain, non-technical language. Provides definition, "
                "what makes a good value, caveats, and the current model's value for that metric. "
                "Use this when asked 'what is [metric]?' or 'explain [metric]'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "metric_name": {
                        "type": "string",
                        "description": (
                            "Name of the metric to explain. Examples: 'accuracy', 'precision', "
                            "'recall', 'f1', 'auc', 'specificity', 'false_positive_rate', "
                            "'false_negative_rate', 'data_drift', 'statistical_parity_difference', "
                            "'disparate_impact', 'calibration_error', 'shap'"
                        ),
                    },
                },
                "required": ["metric_name"],
            },
        ),
        Tool(
            name="orchestrate_query",
            description=(
                "Decompose a complex user query into sub-queries, automatically call "
                "the right tools, and build a structured response with risk mitigations. "
                "Use this when the user asks a broad or multi-part question that spans "
                "multiple areas (e.g. 'Give me a full assessment of this model including "
                "performance, bias risks, and deployment readiness'). Returns tool results, "
                "risk mitigations from a built-in playbook, and a response plan."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_query": {
                        "type": "string",
                        "description": "The user's natural language question about the ML model.",
                    },
                },
                "required": ["user_query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """Handle tool invocation from the nanobot agent."""
    print(f"[ML-RISK-ENGINE] Tool called: {name} | Args: {arguments}", file=sys.stderr)

    try:
        if name == "get_model_performance":
            text = get_model_performance()

        elif name == "get_drift_report":
            drift_type = str(arguments.get("drift_type", "data"))
            text = get_drift_report(drift_type)

        elif name == "get_bias_report":
            text = get_bias_report()

        elif name == "get_data_quality_report":
            text = get_data_quality_report()

        elif name == "get_feature_importance":
            method = str(arguments.get("method", "shap"))
            text = get_feature_importance(method)

        elif name == "assess_deployment_risk":
            mode = str(arguments.get("mode", "classic"))
            model_id = arguments.get("model_id")
            model_type = arguments.get("model_type")
            text = assess_deployment_risk(
                mode=mode,
                model_id=model_id,
                model_type=model_type,
                firewall_path=arguments.get("firewall_path"),
                observability_path=arguments.get("observability_path"),
                performance_path=arguments.get("performance_path"),
                clarity_path=arguments.get("clarity_path"),
            )

        elif name == "explain_metric":
            metric_name = str(arguments.get("metric_name", ""))
            text = explain_metric(metric_name)

        elif name == "orchestrate_query":
            user_query = str(arguments.get("user_query", ""))
            text = orchestrate_query(user_query)

        else:
            text = json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        print(f"[ML-RISK-ENGINE] Error in {name}: {e}", file=sys.stderr)
        text = json.dumps({"error": str(e)})

    return CallToolResult(
        content=[TextContent(type="text", text=text)],
    )


async def main() -> None:
    async with stdio_server() as (read, write):
        init_options = InitializationOptions(
            server_name="ml-risk-engine",
            server_version="1.0.0",
            capabilities={},
        )
        await server.run(read, write, init_options)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
