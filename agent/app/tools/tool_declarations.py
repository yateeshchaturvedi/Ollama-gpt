"""Gemini function declarations generated dynamically from TOOL_REGISTRY."""
from __future__ import annotations

from typing import Any
import google.generativeai as genai
from app.tooling import TOOL_REGISTRY, ToolDescriptor

# Description lookup for common parameters to make tool invocation precise
PARAM_DESCRIPTIONS = {
    "command": "The shell command to run. Restrict to allowed commands.",
    "path": "The path to the file relative to the workspace root.",
    "content": "The text content to write to the file.",
    "repo": "The GitHub repository path in format 'owner/repo'.",
    "run_id": "The unique workflow run identifier (integer).",
    "pr_number": "The pull request number (integer).",
    "per_page": "Number of items to fetch per page.",
    "limit": "Max number of items to return.",
    "base": "The base git reference (e.g. main, master, commit SHA).",
    "head": "The head git reference (e.g. feature-branch, commit SHA).",
    "body": "The markdown comment body content.",
    "repos": "A list of GitHub repository paths in 'owner/repo' format.",
    "job_name": "The name of the Jenkins job.",
    "build_number": "The Jenkins build number (integer).",
    "project": "The Azure DevOps project name.",
    "pipeline_id": "The Azure DevOps pipeline ID (integer).",
    "project_id": "The GitLab project ID or URL-encoded path.",
    "max_chars": "Maximum number of characters to read from logs.",
    "confirmation": "Required confirmation token. Must be 'CONFIRM' to run dangerous commands.",
}


def get_gemini_tools() -> list[genai.protos.Tool]:
    """Build a list of Tool objects for Gemini generative model."""
    declarations = []

    for name, descriptor in TOOL_REGISTRY.items():
        properties = {}
        required = []

        # 1. Required string parameters
        for param in descriptor.required_str:
            properties[param] = genai.protos.Schema(
                type=genai.protos.Type.STRING,
                description=PARAM_DESCRIPTIONS.get(param, f"The '{param}' string parameter.")
            )
            required.append(param)

        # 2. Required integer parameters
        for param in descriptor.required_int:
            properties[param] = genai.protos.Schema(
                type=genai.protos.Type.INTEGER,
                description=PARAM_DESCRIPTIONS.get(param, f"The '{param}' integer parameter.")
            )
            required.append(param)

        # 3. Required string any parameters (can be empty string)
        for param in descriptor.required_str_any:
            properties[param] = genai.protos.Schema(
                type=genai.protos.Type.STRING,
                description=PARAM_DESCRIPTIONS.get(param, f"The '{param}' string parameter.")
            )
            required.append(param)

        # 4. Required list or string parameters (like repos)
        for param in descriptor.required_list_or_str:
            properties[param] = genai.protos.Schema(
                type=genai.protos.Type.ARRAY,
                items=genai.protos.Schema(type=genai.protos.Type.STRING),
                description=PARAM_DESCRIPTIONS.get(param, f"List of '{param}' values.")
            )
            required.append(param)

        # 5. Optional parameters
        for param, default in descriptor.optional_args.items():
            if isinstance(default, int):
                properties[param] = genai.protos.Schema(
                    type=genai.protos.Type.INTEGER,
                    description=PARAM_DESCRIPTIONS.get(param, f"Optional '{param}' parameter (default: {default}).")
                )
            elif isinstance(default, list):
                properties[param] = genai.protos.Schema(
                    type=genai.protos.Type.ARRAY,
                    items=genai.protos.Schema(type=genai.protos.Type.STRING),
                    description=PARAM_DESCRIPTIONS.get(param, f"Optional '{param}' parameter (default: {default}).")
                )
            else:
                properties[param] = genai.protos.Schema(
                    type=genai.protos.Type.STRING,
                    description=PARAM_DESCRIPTIONS.get(param, f"Optional '{param}' parameter (default: '{default}').")
                )

        # 6. Confirmation parameter if needed
        if descriptor.needs_confirmation:
            properties["confirmation"] = genai.protos.Schema(
                type=genai.protos.Type.STRING,
                description=PARAM_DESCRIPTIONS.get("confirmation")
            )

        parameters = genai.protos.Schema(
            type=genai.protos.Type.OBJECT,
            properties=properties,
            required=required
        )

        decl = genai.protos.FunctionDeclaration(
            name=name,
            description=descriptor.description,
            parameters=parameters
        )
        declarations.append(decl)

    # Standard Tool object containing all declarations
    return [genai.protos.Tool(function_declarations=declarations)]
