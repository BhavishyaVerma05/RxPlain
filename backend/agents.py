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
    
    BRAND_MAP = {
        "crocin": "paracetamol",
        "dolo": "paracetamol", 
        "calpol": "paracetamol",
        "augmentin": "amoxicillin clavulanate",
        "pantocid": "pantoprazole",
        "pan": "pantoprazole",
        "mox": "amoxicillin",
        "azithral": "azithromycin",
        "zithromax": "azithromycin",
        "combiflam": "ibuprofen paracetamol",
        "brufen": "ibuprofen",
        "ativan": "lorazepam",
        "flagyl": "metronidazole",
        "metrogyl": "metronidazole",
        "zerodol": "aceclofenac",
        "flexon": "ibuprofen paracetamol",
    }
    
    # Strip common dosage prefixes
    prefix_pattern = r'^(?:Tab\.|Cap\.|Syr\.|Inj\.|Oint\.|Tab|Cap|Syr|Inj|Oint)\s+'
    prescription_text = re.sub(prefix_pattern, '', prescription_text, flags=re.IGNORECASE)

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

    original_drug_name = drug_name
    if drug_name:
        drug_lower = drug_name.lower()
        for brand, generic in BRAND_MAP.items():
            if brand in drug_lower:
                drug_name = generic
                break

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
    
    # Detect if a fixed duration is present in the original text
    _DURATION_PATTERN = re.compile(
        r'x\s*\d+\s*d(?:ays?)?\b|'
        r'\bfor\s+\d+\s*(?:days?|wks?|weeks?|months?)\b|'
        r'\d+[-\s]*(?:day|week|month)\s*course\b|'
        r'\bx\d+\s*(?:wk|wks|week|weeks|mo|months?)',
        re.IGNORECASE
    )
    has_duration = bool(_DURATION_PATTERN.search(prescription_text))
    
    # Extract numeric duration and convert to days
    duration_days = 0
    _DUR_NUM = re.search(
        r'(?:x|for)\s*(\d+)\s*(d(?:ays?)?|wk|wks|weeks?|mo|months?)',
        prescription_text, re.IGNORECASE
    )
    if _DUR_NUM:
        num  = int(_DUR_NUM.group(1))
        unit = _DUR_NUM.group(2).lower()
        if unit.startswith('wk') or unit.startswith('week'):
            duration_days = num * 7
        elif unit.startswith('mo'):
            duration_days = num * 30
        else:
            duration_days = num
    
    # Extract frequency raw abbreviation
    _FREQ_ABBREVS = {"qd", "od", "bid", "tid", "qid", "q4h", "q6h", "q8h", "q12h", "qam", "qpm", "qhs", "qod", "prn", "sos"}
    frequency_raw = ""
    for word in raw_words:
        if word in _FREQ_ABBREVS:
            frequency_raw = word
            break
            
    # Check for Indian 1-1-1 pattern
    digit_freq = re.search(r'\b(\d)-(\d)-(\d)\b', prescription_text)
    decoded_digit_freq = ""
    if digit_freq:
        pattern = f"{digit_freq.group(1)}-{digit_freq.group(2)}-{digit_freq.group(3)}"
        if pattern == "1-1-1":
            frequency_raw = "tid"
            decoded_digit_freq = "three times a day"
        elif pattern == "1-0-1":
            frequency_raw = "bid"
            decoded_digit_freq = "twice a day, morning and night"
        elif pattern == "1-0-0":
            frequency_raw = "qd"
            decoded_digit_freq = "once daily in the morning"
        elif pattern == "0-0-1":
            frequency_raw = "qhs"
            decoded_digit_freq = "once daily at bedtime"
        elif pattern == "1-1-0":
            frequency_raw = "bid"
            decoded_digit_freq = "twice a day, morning and afternoon"
        elif pattern == "0-1-0":
            frequency_raw = "qd"
            decoded_digit_freq = "once daily in the afternoon"
        elif pattern == "0-1-1":
            frequency_raw = "bid"
            decoded_digit_freq = "twice a day, afternoon and night"
    
    prn = False
    if "prn" in raw_words or "sos" in raw_words:
        prn = True
        
    has_route = any(rt in raw_words for rt in {"po", "oral", "iv", "im", "sc", "sl", "top"})
    
    if "od" in raw_words and not has_route:
        flags.append("od is ambiguous (could mean once daily or right eye)")

    decoded_parts = []
    if decoded_digit_freq:
        decoded_parts.append(decoded_digit_freq)
        
    for word in raw_words:
        if word == "od" and has_route:
            decoded_parts.append("once daily")
        elif word in ABBREVIATIONS:
            decoded_parts.append(ABBREVIATIONS[word])
        elif not digit_freq or word not in {"1", "0"}: # Don't re-append digits if part of digit freq pattern
            decoded_parts.append(word)
            
    result = {
        "drug_name": drug_name,
        "display_name": original_drug_name,
        "drug_dose": drug_dose,
        "quantity": quantity,
        "route": "",
        "frequency": "",
        "duration": "",
        "prn": prn,
        "has_duration": has_duration,
        "duration_days": duration_days,
        "frequency_raw": frequency_raw,
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

def get_meal_schedule(freq: str, decoded: str, qty: str) -> str:
    qty_str = qty if qty else "1 dose"
    freq = freq.lower()
    
    if "prn" in freq or "sos" in freq:
        return f"Take {qty_str} only when needed. Do not exceed the prescribed dose in 24 hours."
    
    ac = "before meals" in decoded
    pc = "after meals" in decoded
    hs = "at bedtime" in decoded
    
    if freq in ["qd", "od"]:
        if ac: return f"Take {qty_str} at 7:30 AM, 30 minutes before breakfast."
        if pc: return f"Take {qty_str} after breakfast."
        if hs: return f"Take {qty_str} at bedtime (around 10:00 PM)."
        return f"Take {qty_str} once daily."
    elif freq == "bid":
        if ac: return f"Take {qty_str} at 7:30 AM before breakfast and {qty_str} at 12:30 PM before lunch."
        if pc: return f"Take {qty_str} after breakfast and {qty_str} after dinner."
        return f"Take {qty_str} once in the morning and once in the evening."
    elif freq == "tid":
        if ac: return f"Take {qty_str} 30 minutes before breakfast, before lunch, and before dinner."
        if pc: return f"Take {qty_str} after breakfast, after lunch, and after dinner."
        return f"Take {qty_str} three times a day."
    elif freq == "qid":
        return f"Take {qty_str} at 8:00 AM, 12:00 PM, 4:00 PM, and 8:00 PM."
    
    return f"Take {qty_str} as directed."

def summarizer_agent(parsed_list: list, lookup_list: list, safety_results: list, combined_interactions: list) -> str:
    """
    Agent 4: Calls Groq API to summarize facts in plain English, and appends interactions deterministically.
    """
    is_multi = len(parsed_list) > 1
    
    if is_multi:
        facts_str = ""
        meal_schedules = ""
        for i, p in enumerate(parsed_list):
            facts_str += f"{i+1}.\n"
            facts_str += f"- Drug Name: {p.get('drug_name')}\n"
            facts_str += f"- Dose Amount: {p.get('drug_dose')}\n"
            facts_str += f"- Quantity: {p.get('quantity')}\n"
            facts_str += f"- Instructions: {p.get('decoded_instruction')}\n\n"
            
            meal_schedules += f"{i+1}. {p.get('drug_name')}: {get_meal_schedule(p.get('frequency_raw', ''), p.get('decoded_instruction', ''), p.get('quantity', ''))}\n"
            
        prompt = f"""
    You are a medical summarization assistant. 
    Write a plain-language summary for the patient using ONLY the facts provided below. Do not add external knowledge.
    
    Provided Facts for Medications:
    {facts_str}
       
    Task:
    The patient has been prescribed the following medications. 
    For each one, provide clear dosage instructions in plain English. 
    
    Never mention parsing uncertainty, unclear instructions, or tell the patient to ask their doctor for clarification about the format of the prescription. If a frequency is successfully decoded, state it plainly. Only include medically relevant information in the output.
    
    Write the summary using the following uppercase headings exactly, separated by blank lines:
    
    MEDICATIONS:
    1. [Drug 1 plain language instructions]
    2. [Drug 2 plain language instructions]
    (continue for all drugs)
    
    MEAL SCHEDULE:
    {meal_schedules.strip()}
    """
    else:
        # Existing single-drug logic
        parser_data = parsed_list[0]
        meal_schedule_text = get_meal_schedule(parser_data.get('frequency_raw', ''), parser_data.get('decoded_instruction', ''), parser_data.get('quantity', ''))
        
        prompt = f"""
    You are a medical summarization assistant. 
    Write a plain-language summary for the patient using ONLY the facts provided below. Do not add external knowledge.
    
    Provided Facts:
    - Drug Name: {parser_data.get('drug_name')}
    - Dose Amount: {parser_data.get('drug_dose')}
    - Quantity: {parser_data.get('quantity')}
    - Instructions: {parser_data.get('decoded_instruction')}
       
    Task:
    Never mention parsing uncertainty, unclear instructions, or tell the patient to ask their doctor for clarification about the format of the prescription. If a frequency is successfully decoded, state it plainly. Only include medically relevant information in the output.
    
    Write the summary using the following uppercase headings exactly, separated by blank lines:
    
    DOSAGE INSTRUCTIONS:
    (Write the decoded dosage instructions in plain English here, clearly separating the dose amount from the quantity)
    
    MEAL SCHEDULE:
    {meal_schedule_text}
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
            
    return groq_output.strip()

def apply_guardrails(safety_results: list, combined_interactions: list) -> dict:
    """
    Deterministic safety guardrail function.
    """
    block_flag = False
    reasons = []
    
    for safety_res in safety_results:
        if safety_res.get("boxed_warning") is True:
            block_flag = True
            reasons.append(f"Boxed Warning found for {safety_res.get('target_drug')}.")
            
    if combined_interactions:
        block_flag = True
        for interaction in combined_interactions:
            src = interaction.get('source_drug', 'unknown')
            tgt = interaction.get('medication', 'unknown')
            reasons.append(f"Interaction detected between {src} and {tgt}")
            
    # deduplicate reasons
    reasons = list(dict.fromkeys(reasons))
            
    disclaimer = "This is not medical advice. Confirm all instructions with your pharmacist or doctor before taking any medication."
    
    return {
        "block_flag": block_flag,
        "block_reasons": reasons,
        "disclaimer": disclaimer
    }


def ocr_agent(base64_image: str) -> str:
    """
    Agent 5: Calls Groq Vision model to extract text from a prescription image.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "Error: GROQ_API_KEY not found in environment. Cannot process image."
        
    try:
        client = Groq(api_key=api_key)
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": "Extract only the medication information from this prescription image. Return only the drug name, dose, quantity, frequency, route, and duration for each medication listed. Ignore and do not include: doctor name, clinic name, address, phone number, patient name, date, signature, registration number, or any other administrative details. Format each medication on a new line like: [Drug name] [dose], [quantity] [route] [frequency] [duration]. DO NOT output anything else. No conversational filler, no markdown."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                            },
                        },
                    ],
                }
            ],
            model="meta-llama/llama-4-scout-17b-16e-instruct",
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        return f"Error during OCR extraction: {str(e)}"

