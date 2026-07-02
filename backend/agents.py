import json
import re

ABBREVIATIONS = {
    "po": "by mouth", "iv": "intravenously", "im": "intramuscularly", "sc": "under the skin",
    "sl": "under the tongue", "top": "applied to skin", "od": "right eye", "os": "left eye",
    "ou": "both eyes", "bid": "twice a day", "tid": "three times a day", "qid": "four times a day",
    "qd": "once a day", "q4h": "every 4 hours", "q6h": "every 6 hours", "q8h": "every 8 hours",
    "q12h": "every 12 hours", "qam": "every morning", "qpm": "every evening", "qhs": "at bedtime",
    "qod": "every other day", "prn": "as needed", "ac": "before meals", "pc": "after meals",
    "stat": "immediately", "tab": "tablet", "cap": "capsule", "tabs": "tablets", "caps": "capsules",
    "sol": "solution", "susp": "suspension", "gtt": "drop", "gtts": "drops", "ml": "milliliter",
    "mg": "milligram", "mcg": "microgram", "g": "gram", "tsp": "teaspoon", "tbsp": "tablespoon",
    "u": "units", "iu": "international units", "d": "days", "wk": "weeks", "mo": "months", "ud": "as directed",
    "npo": "nothing by mouth", "dc": "discontinue", "ung": "ointment", "supp": "suppository"
}

def parser_agent(prescription_text: str) -> dict:
    """
    Agent 1: Decodes medical abbreviations using a hardcoded dictionary.
    
    Returns:
        JSON {drug_name, drug_dose, quantity, route, frequency, duration, prn (bool), flags[]}
    """
    flags = []
    
    drug_name = ""
    drug_dose = ""
    quantity = ""
    
    # Match Drug Name and Dose (e.g. Warfarin 5mg)
    dose_match = re.search(r'^([a-zA-Z\s]+)\s+(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|u|iu|%))', prescription_text, re.IGNORECASE)
    if dose_match:
        drug_name = dose_match.group(1).strip()
        drug_dose = dose_match.group(2).strip()
        rest = prescription_text[dose_match.end():].strip(' ,')
    else:
        # Fallback
        name_match = re.search(r'^([a-zA-Z\s]+)', prescription_text)
        if name_match:
            drug_name = name_match.group(1).strip()
            rest = prescription_text[name_match.end():].strip(' ,')
        else:
            rest = prescription_text

    # Match Quantity (e.g. 1 tab, 2 caps, 0.5 ml)
    qty_match = re.search(r'^(\d+(?:\.\d+)?)\s*([a-zA-Z]+)', rest, re.IGNORECASE)
    if qty_match:
        q_num = qty_match.group(1)
        q_unit = qty_match.group(2).lower()
        if q_unit in ABBREVIATIONS:
            q_unit_decoded = ABBREVIATIONS[q_unit]
        else:
            q_unit_decoded = q_unit
        quantity = f"{q_num} {q_unit_decoded}"
        rest = rest[qty_match.end():].strip(' ,')
        
    raw_words = re.findall(r'\b[a-zA-Z]+\b|\d+', rest.lower())
    
    prn = False
    if "prn" in raw_words:
        prn = True
        
    if "od" in raw_words:
        flags.append("od is ambiguous (could mean once daily or right eye)")

    decoded_parts = []
    for word in raw_words:
        if word in ABBREVIATIONS:
            decoded_parts.append(ABBREVIATIONS[word])
        else:
            decoded_parts.append(word)
            
    result = {
        "drug_name": drug_name,
        "drug_dose": drug_dose,
        "quantity": quantity,
        "route": "", 
        "frequency": "", 
        "duration": "", 
        "prn": prn, 
        "flags": flags,
        "decoded_instruction": " ".join(decoded_parts)
    }
    
    return result

async def lookup_agent(drug_name: str, mcp_client) -> dict:
    """
    Agent 2: Uses the MCP client to call the lookup_drug tool.
    """
    try:
        # Assuming the MCP client provides access to tools via call_tool
        result_str = await mcp_client.call_tool("lookup_drug", {"name": drug_name})
        # If result_str is a list with TextContent, extract text
        if hasattr(result_str, 'content') and len(result_str.content) > 0:
            text = result_str.content[0].text
        else:
            text = str(result_str) # Fallback
            
        return json.loads(text)
    except Exception as e:
        return {"found": False, "error": str(e)}

async def safety_agent(generic_name: str, other_meds: list, mcp_client) -> dict:
    """
    Agent 3: Uses the MCP client to call the get_safety_data tool.
    """
    try:
        result_str = await mcp_client.call_tool("get_safety_data", {
            "generic_name": generic_name,
            "other_meds": other_meds
        })
        
        if hasattr(result_str, 'content') and len(result_str.content) > 0:
            text = result_str.content[0].text
        else:
            text = str(result_str)
            
        return json.loads(text)
    except Exception as e:
        return {"error": str(e)}

import os
from groq import Groq

def summarizer_agent(parser_data: dict, lookup_data: dict, safety_data: dict) -> str:
    """
    Agent 4: Calls Groq API to summarize facts in plain English, and appends interactions deterministically.
    """
    # Strict prompt according to requirements
    prompt = f"""
    You are a medical summarization assistant. 
    Write a plain-language summary for the patient using ONLY the facts provided below. Do not add external knowledge.
    
    Provided Facts:
    - Drug Name: {parser_data.get('drug_name')}
    - Dose Amount: {parser_data.get('drug_dose')}
    - Quantity: {parser_data.get('quantity')}
    - Instructions: {parser_data.get('decoded_instruction')}
       
    FDA Safety Warnings:
    - Boxed Warning: {safety_data.get('boxed_warning_text', 'None')}
    - General Warnings: {safety_data.get('warnings', 'None')}
       
    Task:
    Write the summary using the following uppercase headings exactly, separated by blank lines:
    
    DOSAGE INSTRUCTIONS:
    (Write the decoded dosage instructions in plain English here, clearly separating the dose amount from the quantity)
    
    IMPORTANT SAFETY WARNINGS:
    (Summarize the key FDA safety warnings and boxed warnings)
    """
    
    print("========== GROQ PROMPT ==========")
    print(prompt)
    print("=================================")
    
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        groq_output = "Error: GROQ_API_KEY not found in environment. Cannot summarize dosage and warnings."
    else:
        try:
            client = Groq(api_key=api_key)
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model="llama-3.3-70b-versatile",
            )
            groq_output = chat_completion.choices[0].message.content
        except Exception as e:
            groq_output = f"Error during summarization: {str(e)}"
            
    drug_name = parser_data.get('drug_name', 'the prescribed medication')

    if safety_data.get('interaction_detected'):
        meds_found = []
        for interaction in safety_data.get('interactions', []):
            med = interaction.get('medication', 'unknown')
            if med not in meds_found:
                meds_found.append(med)
        meds_str = " and ".join(meds_found)
        
        interaction_section = f"DRUG INTERACTIONS:\n\nWARNING: A known interaction was detected between {drug_name} and {meds_str}. These medications may increase your risk when taken together. Consult your pharmacist or doctor before continuing both medications."
    else:
        interaction_section = "DRUG INTERACTIONS:\n\nNo interactions were detected with your other current medications. Always inform your doctor of all medications you are taking."

    final_output = groq_output.strip() + "\n\n" + interaction_section
    return final_output

def apply_guardrails(safety_data: dict) -> dict:
    """
    Deterministic safety guardrail function.
    """
    block_flag = False
    reasons = []
    
    if safety_data.get("boxed_warning") is True:
        block_flag = True
        reasons.append("This medication has an FDA Boxed Warning (highest safety warning).")
        
    if safety_data.get("interaction_detected") is True:
        block_flag = True
        for interaction in safety_data.get("interactions", []):
            reasons.append(f"Interaction detected with: {interaction.get('medication')}")
            
    disclaimer = "This is not medical advice. Confirm all instructions with your pharmacist or doctor before taking any medication."
    
    return {
        "block_flag": block_flag,
        "block_reasons": reasons,
        "disclaimer": disclaimer
    }

