import asyncio
import sys
import json
from mcp_server import lookup_drug, get_safety_data
from agents import parser_agent, summarizer_agent, apply_guardrails

async def main():
    print("Parsing...", file=sys.stderr)
    parsed = parser_agent("simvastatin 20mg 1 tab po qd")
    drug_name = parsed["drug_name"]
    
    print(f"Lookup for {drug_name}...", file=sys.stderr)
    res1_str = await lookup_drug(drug_name)
    res1 = json.loads(res1_str)
    
    generic_name = res1.get("generic_name")
    
    print("Lookup for clarithromycin...", file=sys.stderr)
    res2_str = await lookup_drug("clarithromycin")
    res2 = json.loads(res2_str)
    
    print("Getting safety data...", file=sys.stderr)
    safety_data_str = await get_safety_data(generic_name, ["clarithromycin"])
    safety_data = json.loads(safety_data_str)
    
    print("Generating summary...", file=sys.stderr)
    summary = summarizer_agent(parsed, res1, safety_data)
    print("\nFINAL SUMMARY:", summary)
    
    print("\nGUARDRAILS:")
    guardrails = apply_guardrails(safety_data)
    print(json.dumps(guardrails, indent=2))
    
if __name__ == "__main__":
    asyncio.run(main())
