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
    """
    FDA_BRAND_MAP = {
        "paracetamol": "acetaminophen",
        "crocin": "acetaminophen",
        "dolo": "acetaminophen"
    }
    
    name_lower = name.lower()
    if name_lower in FDA_BRAND_MAP:
        name = FDA_BRAND_MAP[name_lower]

    base_url = "https://rxnav.nlm.nih.gov/REST"
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Step A: Get RxCUI
        try:
            response = await client.get(f"{base_url}/rxcui.json?name={name}")
            if response.status_code != 200:
                return json.dumps({"found": False, "rxcui": None, "generic_name": None, "matched_name": None})
            data = response.json()
        except Exception as e:
            return json.dumps({"found": False, "rxcui": None, "generic_name": None, "matched_name": None})
        
        rxcui = None
        matched_name = None
        
        if "idGroup" in data and "rxnormId" in data["idGroup"]:
            rxcui = data["idGroup"]["rxnormId"][0]
            matched_name = name
        else:
            # Fallback to approximate term
            try:
                response = await client.get(f"{base_url}/approximateTerm.json?term={name}&maxEntries=1")
                if response.status_code != 200:
                    return json.dumps({"found": False, "rxcui": None, "generic_name": None, "matched_name": None})
                data = response.json()
            except Exception as e:
                return json.dumps({"found": False, "rxcui": None, "generic_name": None, "matched_name": None})
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
        try:
            response = await client.get(f"{base_url}/rxcui/{rxcui}/related.json?tty=IN")
            if response.status_code != 200:
                return json.dumps({"found": True, "rxcui": rxcui, "generic_name": None, "matched_name": matched_name})
            data = response.json()
        except Exception as e:
            return json.dumps({"found": True, "rxcui": rxcui, "generic_name": None, "matched_name": matched_name})
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

DRUG_CLASS_MAP = {
    "amoxicillin": ["amoxicillin", "antibiotic", "penicillin", "antimicrobial"],
    "pantoprazole": ["pantoprazole", "proton pump", "omeprazole", "esomeprazole"],
    "acetaminophen": ["acetaminophen", "paracetamol", "analgesic"],
    "domperidone": ["domperidone", "dopamine"],
    "aspirin": ["aspirin", "salicylate", "antiplatelet", "nsaid"],
    "ibuprofen": ["ibuprofen", "nsaid", "anti-inflammatory"],
    "clarithromycin": ["clarithromycin", "macrolide", "antibiotic"],
    "metronidazole": ["metronidazole", "antibiotic", "antimicrobial"],
    "fluconazole": ["fluconazole", "antifungal", "azole"],
    "simvastatin": ["simvastatin", "statin", "hmg-coa"],
}

FOOD_INTERACTION_MAP = {
    "grapefruit": "Avoid grapefruit and grapefruit juice — it can increase drug levels in your blood.",
    "alcohol": "Avoid alcohol while taking this medication.",
    "dairy": "Avoid dairy products (milk, cheese, yogurt) within 2 hours of taking this medication.",
    "vitamin k": "Maintain consistent intake of Vitamin K foods (leafy greens). Sudden changes can affect how this drug works.",
    "tyramine": "Avoid tyramine-rich foods such as aged cheese, cured meats, and fermented products.",
    "calcium": "Avoid calcium-rich foods or supplements within 2 hours of this medication.",
    "antacid": "Do not take antacids within 2 hours of this medication.",
    "caffeine": "Limit caffeine intake while taking this medication.",
    "iron": "Avoid iron supplements within 2 hours of this medication.",
    "fat": "Take this medication with a fatty meal to improve absorption.",
    "food": "Take this medication with food to reduce stomach upset.",
    "empty stomach": "Take this medication on an empty stomach for best absorption.",
}

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
        "interactions": [],
        "fda_missing_data": False,
        "food_warnings": []
    }
    
    FDA_BRAND_MAP = {
        "paracetamol": "acetaminophen",
        "crocin": "acetaminophen",
        "dolo": "acetaminophen"
    }
    
    generic_lower = generic_name.lower() if generic_name else ""
    if generic_lower in FDA_BRAND_MAP:
        generic_name = FDA_BRAND_MAP[generic_lower]
        
    mapped_other_meds = []
    for m in other_meds:
        m_lower = m.lower() if m else ""
        if m_lower in FDA_BRAND_MAP:
            mapped_other_meds.append(FDA_BRAND_MAP[m_lower])
        else:
            mapped_other_meds.append(m)
    other_meds = mapped_other_meds
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Step A: openFDA label
        if generic_name:
            fda_url = f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:\"{generic_name}\"&limit=1"
            try:
                response = await client.get(fda_url)
            except Exception:
                class DummyResponse:
                    status_code = 500
                response = DummyResponse()
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
                        
                    # Check interactions using openFDA drug_interactions field or warnings field
                    import sys
                    full_text = ""
                    if "drug_interactions" in label:
                        full_text = label["drug_interactions"][0]
                    elif "warnings" in label:
                        full_text = label["warnings"][0]
                        
                    if full_text:
                        valid_other_meds = [m for m in other_meds if m]
                        
                        # DEBUG 1: full list being checked
                        
                        if generic_name.lower() == "warfarin":
                            test_terms = ["antibiotic", "penicillin", "acetaminophen", "paracetamol", "proton pump", "omeprazole", "antimicrobial"]
                            lower_full_text = full_text.lower()
                            for term in test_terms:
                                found = term in lower_full_text
                        
                        lower_full = full_text.lower()
                        for med in valid_other_meds:
                            med_lower = med.lower()
                            
                            # 1. Look up in map or fall back to just the name
                            search_terms = DRUG_CLASS_MAP.get(med_lower, [med_lower])
                            
                            # 2. Search for ANY synonym
                            matched = False
                            for term in search_terms:
                                idx = lower_full.find(term)
                                if idx != -1:
                                    result["interaction_detected"] = True
                                    
                                    # Find sentence boundaries around idx
                                    sentence_start = 0
                                    for pos in range(idx - 1, -1, -1):
                                        if full_text[pos] in ['.', '\n', ';']:
                                            sentence_start = pos + 1
                                            break
                                            
                                    sentence_end = len(full_text)
                                    for pos in range(idx, len(full_text)):
                                        if full_text[pos] in ['.', '\n', ';']:
                                            sentence_end = pos + 1
                                            break
                                            
                                    excerpt = full_text[sentence_start:sentence_end].strip()
                                    
                                    # 4. Record which synonym matched
                                    result["interactions"].append({
                                        "medication": med,
                                        "matched_term": term,
                                        "excerpt": excerpt
                                    })
                                    matched = True
                                    break
                            
                            if not matched:
                                pass
                        
                        # Food and Alcohol Interaction Check
                        for food_term, food_msg in FOOD_INTERACTION_MAP.items():
                            if food_term in lower_full:
                                if food_msg not in result["food_warnings"]:
                                    result["food_warnings"].append(food_msg)
                                    
                    else:
                        result["fda_missing_data"] = True
                        missing_msg = f"Safety data for {generic_name} is not available in the FDA database. This drug may not be FDA-approved. Consult your pharmacist for complete interaction information."
                        result["warnings"] = missing_msg
                else:
                    # 200 OK but no results
                    result["fda_missing_data"] = True
                    missing_msg = f"Safety data for {generic_name} is not available in the FDA database. This drug may not be FDA-approved. Consult your pharmacist for complete interaction information."
                    result["warnings"] = missing_msg
            else:
                # Non-200 status code (e.g. 404)
                result["fda_missing_data"] = True
                missing_msg = f"Safety data for {generic_name} is not available in the FDA database. This drug may not be FDA-approved. Consult your pharmacist for complete interaction information."
                result["warnings"] = missing_msg

    return json.dumps(result)

if __name__ == "__main__":
    mcp.run()
