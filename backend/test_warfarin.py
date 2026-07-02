import asyncio
import sys
from mcp_server import lookup_drug, get_safety_data
from agents import parser_agent

async def main():
    print("Parsing...", file=sys.stderr)
    parsed = parser_agent("Warfarin 5mg, 1 tab po qd")
    drug_name = parsed["drug_name"]
    
    print(f"Lookup for {drug_name}...", file=sys.stderr)
    res1_str = await lookup_drug(drug_name)
    import json
    res1 = json.loads(res1_str)
    
    generic_name = res1.get("generic_name")
    rxcui_warfarin = res1.get("rxcui")
    
    print("Lookup for Aspirin...", file=sys.stderr)
    res2_str = await lookup_drug("aspirin")
    res2 = json.loads(res2_str)
    rxcui_aspirin = res2.get("rxcui")
    
    print("Getting safety data...", file=sys.stderr)
    safety_data_str = await get_safety_data(generic_name, ["aspirin"])
    safety_data = json.loads(safety_data_str)
    
    from agents import summarizer_agent, apply_guardrails
    print("Generating summary...", file=sys.stderr)
    summary = summarizer_agent(parsed, res1, safety_data)
    print("\nFINAL SUMMARY:", summary)
    
    print("\nGUARDRAILS:")
    guardrails = apply_guardrails(safety_data)
    print(json.dumps(guardrails, indent=2))
    
if __name__ == "__main__":
    asyncio.run(main())
