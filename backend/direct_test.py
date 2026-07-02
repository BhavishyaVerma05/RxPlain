import asyncio
from mcp_server import lookup_drug, get_safety_data
from agents import parser_agent

async def main():
    print("--- Test Parser ---")
    parsed = parser_agent("Lisinopril 10mg, 1 tab po bid")
    print("Parsed:", parsed)
    
    print("\n--- Test Lookup ---")
    drug_name = parsed["drug_name"]
    res1 = await lookup_drug(drug_name)
    print("Lookup result:", res1)
    
    print("\n--- Test Safety Data ---")
    import json
    res1_dict = json.loads(res1)
    generic_name = res1_dict.get("generic_name")
    rxcui = res1_dict.get("rxcui")
    
    # Passing the primary rxcui + another one to test interactions
    # 1191 is aspirin
    res2 = await get_safety_data(generic_name, [rxcui, "1191"])
    print("Safety result:", res2)

if __name__ == "__main__":
    asyncio.run(main())
