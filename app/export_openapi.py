import json
import os
from typing import Dict, Any
from app.main import app

def generate_markdown_contract(openapi_spec: Dict[str, Any]) -> str:
    lines = []
    lines.append("# DataPulse API Contract")
    lines.append("")
    lines.append("This document outlines the API contract for the **DataPulse** backend, designed to interface seamlessly with the external Lovable frontend.")
    lines.append("")
    lines.append("## General Information")
    lines.append(f"- **API Title**: {openapi_spec.get('info', {}).get('title', 'DataPulse API')}")
    lines.append(f"- **Version**: {openapi_spec.get('info', {}).get('version', '1.0.0')}")
    lines.append("- **Authentication**: Bearer Token (`Authorization: Bearer <token>`)")
    lines.append("- **Trailing Slash Handling**: All endpoints work identically with and without trailing slash (`redirect_slashes=False`)")
    lines.append("- **CORS**: Supports exact origin list and regex (`https://.*\\.(lovable\\.app|lovableproject\\.com|lovable\\.dev)$`)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Endpoints Summary")
    lines.append("")
    lines.append("| Method | Endpoint | Summary | Auth Required |")
    lines.append("|---|---|---|---|")

    paths = openapi_spec.get("paths", {})
    sorted_paths = sorted(paths.keys())

    for path in sorted_paths:
        methods = paths[path]
        for method, details in methods.items():
            if method.lower() not in ("get", "post", "put", "delete", "patch"):
                continue
            summary = details.get("summary") or details.get("description", "").split("\n")[0] or "N/A"
            # Check security
            auth_req = "Yes" if "security" in details or "Bearer" in str(details) else "Optional / No"
            if "/health" in path or "/auth/login" in path or "/auth/register" in path:
                auth_req = "No"
            lines.append(f"| `{method.upper()}` | `{path}` | {summary} | {auth_req} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Detailed Endpoint Specifications")
    lines.append("")

    for path in sorted_paths:
        methods = paths[path]
        for method, details in methods.items():
            if method.lower() not in ("get", "post", "put", "delete", "patch"):
                continue
            method_upper = method.upper()
            summary = details.get("summary") or details.get("description", "")
            tags = ", ".join(details.get("tags", ["General"]))

            lines.append(f"### `{method_upper} {path}`")
            lines.append(f"**Tags**: {tags}  ")
            if summary:
                lines.append(f"**Description**: {summary}  ")
            lines.append("")

            # Request Body
            req_body = details.get("requestBody")
            if req_body:
                lines.append("#### Request Body")
                content = req_body.get("content", {})
                for c_type, c_val in content.items():
                    schema_ref = c_val.get("schema", {})
                    ref = schema_ref.get("$ref") or schema_ref.get("title") or "Custom Schema"
                    lines.append(f"- **Content-Type**: `{c_type}`")
                    lines.append(f"- **Schema**: `{ref.split('/')[-1]}`")
                lines.append("")

            # Parameters
            params = details.get("parameters", [])
            if params:
                lines.append("#### Parameters")
                lines.append("| Name | In | Required | Type | Description |")
                lines.append("|---|---|---|---|---|")
                for p in params:
                    p_name = p.get("name", "")
                    p_in = p.get("in", "")
                    p_req = "Yes" if p.get("required") else "No"
                    p_type = p.get("schema", {}).get("type", "string")
                    p_desc = p.get("description", "")
                    lines.append(f"| `{p_name}` | {p_in} | {p_req} | `{p_type}` | {p_desc} |")
                lines.append("")

            # Responses & Error codes
            responses = details.get("responses", {})
            lines.append("#### Responses & Error Codes")
            lines.append("| Code | Meaning | Schema / Content |")
            lines.append("|---|---|---|")
            for code, resp_val in responses.items():
                desc = resp_val.get("description", "")
                r_content = resp_val.get("content", {})
                content_type = list(r_content.keys())[0] if r_content else "None"
                schema_info = "N/A"
                if r_content:
                    r_schema = list(r_content.values())[0].get("schema", {})
                    schema_info = r_schema.get("$ref", "").split("/")[-1] or r_schema.get("type", "object")
                lines.append(f"| `{code}` | {desc} | `{schema_info}` ({content_type}) |")

            lines.append("")
            lines.append("---")
            lines.append("")

    # Error code reference section
    lines.append("## Standard Error Codes & Handling")
    lines.append("")
    lines.append("| HTTP Code | Error | Resolution |")
    lines.append("|---|---|---|")
    lines.append("| `400 Bad Request` | Missing file, duplicate email, or invalid parameters | Check request parameters and payload structure. |")
    lines.append("| `401 Unauthorized` | Missing or invalid `Authorization: Bearer <token>` header | Login to obtain a valid access token and include it in request headers. |")
    lines.append("| `402 Payment Required / Insufficient Balance` | Insufficient credit balance | Upload more datasets to earn credits or top up. |")
    lines.append("| `404 Not Found` | Dataset or evaluation ID not found | Verify resource ID exists in the system. |")
    lines.append("| `422 Unprocessable Entity` | Schema validation error (e.g. empty CSV or invalid types) | Inspect validation message and ensure payload matches schema. |")
    lines.append("| `500 Internal Server Error` | Unexpected backend failure | Check backend logs and retry. |")
    lines.append("")

    return "\n".join(lines)


def export():
    # 1. Fetch OpenAPI specification from FastAPI app
    openapi_spec = app.openapi()

    # 2. Write openapi.json in project root
    openapi_path = "openapi.json"
    with open(openapi_path, "w", encoding="utf-8") as f:
        json.dump(openapi_spec, f, indent=2)
    print(f"Exported OpenAPI JSON to: {os.path.abspath(openapi_path)}")

    # 3. Create docs directory if not existing
    os.makedirs("docs", exist_ok=True)
    doc_path = os.path.join("docs", "API_CONTRACT.md")

    # 4. Generate Markdown documentation
    markdown_content = generate_markdown_contract(openapi_spec)
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    print(f"Exported human-readable API Contract to: {os.path.abspath(doc_path)}")


if __name__ == "__main__":
    export()
