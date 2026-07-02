import json
import httpx
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("RxPlain-FDA-RxNorm")

@mcp.tool()
async def lookup_drug(name: str) -> str:
    """
    Looks up a drug in the RxNorm API to get its RxCUI and generic name.
    
    Args:
        name: The name of the drug to look up.
        
    Returns:
        JSON string containing {rxcui, generic_name, matched_name, found (bool)}.
    """
    base_url = "https://rxnav.nlm.nih.gov/REST"
    async with httpx.AsyncClient() as client:
        # Step A: Get RxCUI
        response = await client.get(f"{base_url}/rxcui.json?name={name}")
        data = response.json()
        
        rxcui = None
        matched_name = None
        
        if "idGroup" in data and "rxnormId" in data["idGroup"]:
            rxcui = data["idGroup"]["rxnormId"][0]
            matched_name = name
        else:
            # Fallback to approximate term
            response = await client.get(f"{base_url}/approximateTerm.json?term={name}&maxEntries=1")
            data = response.json()
            if "approximateGroup" in data and "candidate" in data["approximateGroup"]:
                candidate = data["approximateGroup"]["candidate"][0]
                rxcui = candidate["rxcui"]
                # We can do a quick lookup to get the name of this rxcui if needed
                matched_name = candidate.get("name", name)
                
        if not rxcui:
            return json.dumps({
                "found": False,
                "rxcui": None,
                "generic_name": None,
                "matched_name": None
            })
            
        # Step B: Get generic name
        response = await client.get(f"{base_url}/rxcui/{rxcui}/related.json?tty=IN")
        data = response.json()
        generic_name = None
        
        if "relatedGroup" in data and "conceptGroup" in data["relatedGroup"]:
            for group in data["relatedGroup"]["conceptGroup"]:
                if "conceptProperties" in group:
                    # Take the first generic name found
                    generic_name = group["conceptProperties"][0]["name"]
                    break
                    
        return json.dumps({
            "found": True,
            "rxcui": rxcui,
            "generic_name": generic_name or matched_name,
            "matched_name": matched_name
        })

@mcp.tool()
async def get_safety_data(generic_name: str, other_meds: list[str]) -> str:
    """
    Gets safety data from openFDA and checks for interactions within the label.
    
    Args:
        generic_name: The generic name of the primary drug.
        other_meds: A list of names of other medications the user is taking.
        
    Returns:
        JSON string containing warnings, adverse_reactions, contraindications, boxed_warning (bool),
        boxed_warning_text, interaction_detected (bool), interactions[].
    """
    result = {
        "warnings": "",
        "adverse_reactions": "",
        "contraindications": "",
        "boxed_warning": False,
        "boxed_warning_text": "",
        "interaction_detected": False,
        "interactions": []
    }
    
    async with httpx.AsyncClient() as client:
        # Step A: openFDA label
        if generic_name:
            fda_url = f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:\"{generic_name}\"&limit=1"
            response = await client.get(fda_url)
            if response.status_code == 200:
                data = response.json()
                if "results" in data and len(data["results"]) > 0:
                    label = data["results"][0]
                    
                    if "warnings" in label:
                        result["warnings"] = label["warnings"][0]
                    if "adverse_reactions" in label:
                        result["adverse_reactions"] = label["adverse_reactions"][0]
                    if "contraindications" in label:
                        result["contraindications"] = label["contraindications"][0]
                    if "boxed_warning" in label:
                        result["boxed_warning"] = True
                        result["boxed_warning_text"] = label["boxed_warning"][0]
                        
                    # Check interactions using openFDA drug_interactions field
                    import sys
                    if "drug_interactions" in label:
                        full_text = label["drug_interactions"][0]
                        valid_other_meds = [m for m in other_meds if m]
                        for med in valid_other_meds:
                            lower_full = full_text.lower()
                            idx = lower_full.find(med.lower())
                            if idx != -1:
                                result["interaction_detected"] = True
                                start = max(0, idx - 100)
                                end = min(len(full_text), idx + 100)
                                result["interactions"].append({
                                    "medication": med,
                                    "excerpt": full_text[start:end]
                                })

    return json.dumps(result)

if __name__ == "__main__":
    mcp.run()
