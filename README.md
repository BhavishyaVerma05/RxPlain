# RxPlain: Prescription Plain-Language Translator

RxPlain is a full-stack web application designed to translate medical shorthand on prescriptions into plain-language instructions, while simultaneously checking real-time FDA safety data for contraindications and cross-drug interactions.

## Architecture

RxPlain is built using the Agent Development Kit (ADK) pattern, running an event loop and exposing an HTTP API. It leverages the Model Context Protocol (MCP) to standardize external tool connections.

- **Frontend**: A single-page Vanilla HTML/CSS/JS application that collects prescription strings and other active medications.
- **Backend API**: A standard Python `HTTPServer` (`server.py`) serving the frontend and exposing a `/api/translate` endpoint.
- **MCP Server**: (`mcp_server.py`) Provides two critical MCP tools:
  - `lookup_drug`: Queries the NIH RxNorm API to map drug shorthand into standard generic concepts.
  - `get_safety_data`: Queries the openFDA label API to extract boxed warnings, adverse reactions, and check for active drug interactions across the label's `drug_interactions` text block.
- **AI Agents**: (`agents.py`) A chain of ADK-native agents handles the request:
  1. **Parser Agent**: Decodes medical shorthand (e.g. `po bid` -> `by mouth twice a day`) via a hardcoded dictionary mapping.
  2. **Lookup Agent**: Standardizes the parsed drug name against RxNorm.
  3. **Safety Agent**: Pulls FDA label safety data and performs string-matching to detect critical interactions.
  4. **Summarizer Agent**: Sends the parsed dosage and safety warnings to Groq's `llama-3.3-70b-versatile` LLM to generate a plain-language summary for the patient.

The final summary combines the LLM's plain-language output with a deterministically generated, un-ignorable interaction warning section if any interactions are detected.

## Getting Started

1. Set your `GROQ_API_KEY` in your environment.
2. Ensure you have the required dependencies (`google-adk`, `mcp`, `httpx`, `groq`).
3. Run the backend server:
   ```bash
   python backend/server.py
   ```
4. Access the web interface at `http://localhost:8080`.

## Testing
Test scripts are included to test the API toolchain without starting the web server:
- `python backend/test_warfarin.py`
- `python backend/test_simvastatin.py`
