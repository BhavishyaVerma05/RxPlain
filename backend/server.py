import json
import asyncio
import os
import re
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

REQUIRED_ENV_VARS = [
    "GROQ_API_KEY", "FIREBASE_API_KEY", "FIREBASE_AUTH_DOMAIN",
    "FIREBASE_PROJECT_ID", "FIREBASE_STORAGE_BUCKET",
    "FIREBASE_MESSAGING_SENDER_ID", "FIREBASE_APP_ID"
]
missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
if missing_vars:
    import sys
    print(f"CRITICAL ERROR: Missing required environment variables: {', '.join(missing_vars)}")
    sys.exit(1)
import time
from collections import defaultdict

# IP -> [count, reset_time]
rate_limits = defaultdict(lambda: [0, 0])



# Import agents
from agents import parser_agent, lookup_agent, safety_agent, summarizer_agent, apply_guardrails, ocr_agent

INGREDIENT_GROUPS = {
    "paracetamol_group": [
        "acetaminophen", "paracetamol", "tylenol", "panadol",
        "calpol", "dolo", "crocin"
    ],
    "ibuprofen_group": [
        "ibuprofen", "advil", "nurofen", "brufen"
    ],
    "aspirin_group": [
        "aspirin", "acetylsalicylic acid", "disprin"
    ],
    "antacid_group": [
        "pantoprazole", "omeprazole", "esomeprazole", 
        "lansoprazole", "rabeprazole"
    ],
    "antihistamine_group": [
        "cetirizine", "loratadine", "fexofenadine", 
        "chlorpheniramine", "diphenhydramine"
    ],
    "antibiotic_group": [
        "amoxicillin", "azithromycin", "clarithromycin",
        "doxycycline", "ciprofloxacin", "metronidazole"
    ],
}

def check_duplicate_therapy(all_drugs: list) -> list:
    warnings = []
    
    for group_name, group_drugs in INGREDIENT_GROUPS.items():
        matched_indices = []
        for i, drug in enumerate(all_drugs):
            generic = drug.get("generic")
            if not generic:
                continue
            generic_lower = generic.lower()
            if any(group_drug in generic_lower for group_drug in group_drugs):
                matched_indices.append(i)
                
        if len(matched_indices) >= 2:
            drugs = [all_drugs[idx] for idx in matched_indices]
            warnings.append({
                "drug1": drugs[0]["display"],
                "drug2": drugs[1]["display"]
            })
            
    return warnings

# Import FastMCP server setup
from mcp_server import mcp

class RxPlainHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Configure CORS
        allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost,http://127.0.0.1,https://your-cloudrun-url.a.run.app").split(",")
        origin = self.headers.get("Origin")
        if origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()
        
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/translate":
            # Rate limiting
            client_ip = self.client_address[0]
            current_time = time.time()
            limit_data = rate_limits[client_ip]
            
            if current_time > limit_data[1]:
                # Reset window (1 minute)
                limit_data[0] = 1
                limit_data[1] = current_time + 60
            else:
                limit_data[0] += 1
                
            if limit_data[0] > 10:
                self.send_response(429)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Too many requests. Please wait a moment before translating again."}).encode('utf-8'))
                return

            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                prescription_text = data.get("prescription", "")
                other_meds_text = data.get("other_meds", "")
                
                def sanitize_input(text):
                    if not text: return ""
                    text = text.strip()
                    text = re.sub(r'<[^>]*>', '', text)
                    if len(text) > 2000:
                        text = text[:2000]
                    return text
                
                prescription_text = sanitize_input(prescription_text)
                other_meds_text = sanitize_input(other_meds_text)
                
                if not prescription_text:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Prescription text cannot be empty."}).encode('utf-8'))
                    return
                
                # We need an event loop for async agents
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self.run_pipeline(prescription_text, other_meds_text))
                loop.close()
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        elif self.path == "/api/ocr":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                base64_image = data.get("image", "")
                
                # Call OCR agent directly
                extracted_text = ocr_agent(base64_image)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"extracted_text": extracted_text}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        else:
            super().do_POST()

    def do_GET(self):
        if self.path == '/api/config':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            config = {
                "apiKey": os.getenv("FIREBASE_API_KEY"),
                "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
                "projectId": os.getenv("FIREBASE_PROJECT_ID"),
                "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
                "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
                "appId": os.getenv("FIREBASE_APP_ID"),
                "measurementId": os.getenv("FIREBASE_MEASUREMENT_ID")
            }
            self.wfile.write(json.dumps(config).encode('utf-8'))
            return

        # Serve frontend files
        if self.path == '/':
            self.path = '/frontend/index.html'
        elif not self.path.startswith('/frontend/'):
            self.path = '/frontend' + self.path
        return super().do_GET()

    async def run_pipeline(self, prescription: str, other_meds: str):
        from mcp_server import lookup_drug, get_safety_data
        
        # Split by numbered entries first (e.g., "1.", "2.")
        raw_entries = re.split(r'(?:^|\n)\s*\d+\.\s+', prescription)
        raw_drugs = []
        for entry in raw_entries:
            if not entry.strip():
                continue
            # Then split by newlines or semicolons
            sub_entries = [d.strip() for d in re.split(r'[\n;]', entry) if d.strip()]
            raw_drugs.extend(sub_entries)
            
        if not raw_drugs:
            return {"success": False, "message": "No prescription text provided."}
            
        parsed_list = []
        lookup_list = []
        
        for raw_drug in raw_drugs:
            parsed = parser_agent(raw_drug)
            drug_name = parsed.get("drug_name")
            if not drug_name:
                # Treat as instruction context modifier for the previous drug
                if parsed_list:
                    prev = parsed_list[-1]
                    if parsed.get("decoded_instruction"):
                        prev["decoded_instruction"] += f" ({parsed['decoded_instruction']})"
                    if parsed.get("prn"):
                        prev["prn"] = True
                continue
                
            lookup_res_str = await lookup_drug(drug_name)
            lookup_res = json.loads(lookup_res_str)
            if not lookup_res.get("found"):
                # If no drug dose was specified, it might be an instruction line (e.g. "After food")
                if parsed_list and not parsed.get("drug_dose"):
                    prev = parsed_list[-1]
                    if parsed.get("decoded_instruction"):
                        prev["decoded_instruction"] += f" ({raw_drug})"
                    if parsed.get("prn"):
                        prev["prn"] = True
                    continue
                else:
                    return {
                        "success": False,
                        "message": f"Drug '{drug_name}' not recognized. Please check the spelling.",
                        "disclaimer": "This is not medical advice. Confirm all instructions with your pharmacist or doctor before taking any medication."
                    }
            parsed["display_name"] = parsed.get("display_name") or drug_name
            parsed["generic_name"] = lookup_res.get("generic_name") or drug_name
            
            parsed_list.append(parsed)
            lookup_list.append(lookup_res)
            
        if not parsed_list:
            return {"success": False, "message": "Could not parse any medications."}
            
        # Lookup external other meds
        external_other_med_names = []
        external_map = {} # generic_lower -> original input
        if other_meds:
            meds_list = [m.strip() for m in other_meds.split(",") if m.strip()]
            for m in meds_list:
                m_res_str = await lookup_drug(m)
                m_res = json.loads(m_res_str)
                if m_res.get("found") and m_res.get("generic_name"):
                    gen = m_res.get("generic_name")
                    external_other_med_names.append(gen)
                    external_map[gen.lower()] = m
                else:
                    external_other_med_names.append(m)
                    external_map[m.lower()] = m
                    
        # Safety Agent Loop
        safety_results = []
        combined_interactions = []
        
        for i in range(len(lookup_list)):
            target_generic = lookup_list[i].get("generic_name")
            
            # other drugs in prescription after i
            prescription_other_generics = [
                lookup_list[j].get("generic_name") for j in range(i+1, len(lookup_list))
            ]
            
            # combine with external
            drugs_to_check_against = prescription_other_generics + external_other_med_names
            
            # Filter to avoid self-matches (exact or substring)
            filtered_drugs = []
            target_lower = target_generic.lower() if target_generic else ""
            for d in drugs_to_check_against:
                d_lower = d.lower() if d else ""
                if not d_lower or not target_lower:
                    filtered_drugs.append(d)
                    continue
                if d_lower in target_lower or target_lower in d_lower:
                    continue
                filtered_drugs.append(d)
            
            drugs_to_check_against = filtered_drugs
            
            safety_res_str = await get_safety_data(target_generic, drugs_to_check_against)
            safety_res = json.loads(safety_res_str)
            
            # Attach the drug name so we know who these warnings belong to
            safety_res["target_drug"] = parsed_list[i].get("display_name")
            safety_results.append(safety_res)
            
            if safety_res.get("interaction_detected"):
                for interaction in safety_res.get("interactions", []):
                    interaction["source_drug"] = parsed_list[i].get("display_name")
                    
                    # Map interaction medication generic name back to display name
                    other_generic = interaction.get("medication")
                    other_generic_lower = other_generic.lower() if other_generic else ""
                    
                    found_display = None
                    for p in parsed_list:
                        if p.get("generic_name", "").lower() == other_generic_lower:
                            found_display = p.get("display_name")
                            break
                    if not found_display:
                        found_display = external_map.get(other_generic_lower)
                        
                    if found_display:
                        interaction["medication"] = found_display
                        
                    combined_interactions.append(interaction)
                    
        # Collect food warnings
        combined_food_warnings = []
        for sr in safety_results:
            for fw in sr.get("food_warnings", []):
                if fw not in combined_food_warnings:
                    combined_food_warnings.append(fw)
                    
        # Collect side effects for frontend
        side_effects_list = []
        for sr in safety_results:
            drug = sr.get("target_drug")
            common = sr.get("adverse_reactions", "")
            serious = sr.get("warnings", "")
            if sr.get("boxed_warning_text"):
                serious = "BOXED WARNING: " + sr.get("boxed_warning_text") + "\n\n" + serious
            if common or serious:
                side_effects_list.append({
                    "drugName": drug,
                    "common": common,
                    "serious": serious
                })
                
        # Check duplicate therapy
        all_drugs_for_dup = []
        for p in parsed_list:
            all_drugs_for_dup.append({
                "display": p.get("display_name"),
                "generic": p.get("generic_name")
            })
        for ext_gen in external_other_med_names:
            ext_gen_lower = ext_gen.lower() if ext_gen else ""
            original_input = external_map.get(ext_gen_lower, ext_gen)
            all_drugs_for_dup.append({
                "display": original_input,
                "generic": ext_gen
            })
        duplicate_warnings = check_duplicate_therapy(all_drugs_for_dup)
                    
        # Collect missing fda drugs
        missing_fda_drugs = []
        for sr in safety_results:
            if sr.get("fda_missing_data") and sr.get("target_drug"):
                missing_fda_drugs.append(sr.get("target_drug"))
                
        # Add mealSchedule to each parsed item
        from agents import get_meal_schedule
        for p in parsed_list:
            p["mealSchedule"] = get_meal_schedule(p.get("frequency_raw", ""), p.get("decoded_instruction", ""), p.get("quantity", ""))
            
        # 4. Summarizer Agent
        summary = summarizer_agent(parsed_list, lookup_list, safety_results, combined_interactions)
        
        # Guardrails
        guardrails = apply_guardrails(safety_results, combined_interactions)
        
        return {
            "success": True,
            "summary": summary,
            "interactionsList": combined_interactions,
            "missingFdaDrugs": missing_fda_drugs,
            "medications": parsed_list,
            "guardrails": guardrails,
            "foodWarnings": combined_food_warnings,
            "duplicateWarnings": duplicate_warnings,
            "sideEffects": side_effects_list,
            "drugNames": [p.get("display_name") or p.get("drug_name") for p in parsed_list if p.get("display_name") or p.get("drug_name")],
            "hasDuration": any(p.get("has_duration", False) for p in parsed_list),
            "frequency": parsed_list[0].get("frequency_raw", "") if parsed_list else "",
            "frequencyByDrug": {
                (p.get("display_name") or p.get("drug_name")): p.get("frequency_raw", "")
                for p in parsed_list if p.get("display_name") or p.get("drug_name")
            },
            "durationByDrug": {
                (p.get("display_name") or p.get("drug_name")): p.get("duration_days", 0)
                for p in parsed_list if p.get("display_name") or p.get("drug_name")
            }
        }

def run_server(port=8080):
    # Change directory to root so /frontend/index.html works
    # assuming we run from root dir
    server_address = ('', port)
    httpd = HTTPServer(server_address, RxPlainHandler)
    print(f"Starting ADK-native RxPlain server on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    run_server(port)
