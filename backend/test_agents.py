import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Import our agents
from agents import parser_agent, lookup_agent, safety_agent

async def test_mcp_and_agents():
    # Start the MCP server using stdio_client
    server_params = StdioServerParameters(
        command="python",
        args=["backend/mcp_server.py"]
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()
            
            # --- Test Agent 1: Parser ---
            print("--- Testing Agent 1: Parser ---")
            prescription = "Lisinopril 10mg, 1 tab po bid"
            print(f"Input: {prescription}")
            parsed = parser_agent(prescription)
            print(f"Output: {json.dumps(parsed, indent=2)}")
            print()
            
            # --- Test Agent 2: Lookup ---
            print("--- Testing Agent 2: Lookup ---")
            drug_name = parsed["drug_name"]
            print(f"Looking up: {drug_name}")
            lookup_result = await lookup_agent(drug_name, session)
            print(f"Output: {json.dumps(lookup_result, indent=2)}")
            print()
            
            # --- Test Agent 3: Safety ---
            print("--- Testing Agent 3: Safety ---")
            generic_name = lookup_result.get("generic_name")
            rxcui = lookup_result.get("rxcui")
            
            # Let's pretend the user is also taking Aspirin (rxcui: 1191) to test interactions
            other_rxcuis = ["1191"]
            print(f"Getting safety data for {generic_name} (RxCUI: {rxcui}) and Aspirin (RxCUI: 1191)")
            safety_result = await safety_agent(generic_name, rxcui, other_rxcuis, session)
            print(f"Output: {json.dumps(safety_result, indent=2)}")
            print()

if __name__ == "__main__":
    asyncio.run(test_mcp_and_agents())
