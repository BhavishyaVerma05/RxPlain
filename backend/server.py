import json
import asyncio
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Import agents
from agents import parser_agent, lookup_agent, safety_agent, summarizer_agent, apply_guardrails

# Import FastMCP server setup
from mcp_server import mcp

class RxPlainHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/api/translate":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                prescription_text = data.get("prescription", "")
                other_meds_text = data.get("other_meds", "")
                
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
        else:
            super().do_POST()

    def do_GET(self):
        # Serve frontend files
        if self.path == '/':
            self.path = '/frontend/index.html'
        elif not self.path.startswith('/frontend/'):
            self.path = '/frontend' + self.path
        return super().do_GET()

    async def run_pipeline(self, prescription: str, other_meds: str):
        # 1. Parser Agent
        parsed = parser_agent(prescription)
        
        # We will directly call the MCP tool functions for simplicity since it's a single process
        # This bypasses the stdio overhead and fits "single container, single process"
        from mcp_server import lookup_drug, get_safety_data
        
        # 2. Lookup Agent
        drug_name = parsed.get("drug_name")
        lookup_res_str = await lookup_drug(drug_name)
        lookup_res = json.loads(lookup_res_str)
        
        if not lookup_res.get("found"):
            return {
                "success": False,
                "message": "Drug not recognized. Please check the spelling or consult your pharmacist.",
                "disclaimer": "This is not medical advice. Confirm all instructions with your pharmacist or doctor before taking any medication."
            }
            
        rxcui = lookup_res.get("rxcui")
        generic_name = lookup_res.get("generic_name")
        
        # Lookup other medications to get their generic names
        other_med_names = []
        if other_meds:
            meds_list = [m.strip() for m in other_meds.split(",") if m.strip()]
            for m in meds_list:
                m_res_str = await lookup_drug(m)
                m_res = json.loads(m_res_str)
                if m_res.get("found") and m_res.get("generic_name"):
                    other_med_names.append(m_res.get("generic_name"))
                else:
                    other_med_names.append(m)
        
        # 3. Safety Agent
        safety_res_str = await get_safety_data(generic_name, other_med_names)
        safety_res = json.loads(safety_res_str)
        
        # If openFDA returned empty warnings, we handle gracefully
        if not safety_res.get("warnings") and not safety_res.get("boxed_warning"):
             # It means openFDA had no label or no warnings extracted.
             pass
             
        # 4. Summarizer Agent
        summary = summarizer_agent(parsed, lookup_res, safety_res)
        
        # Guardrails
        guardrails = apply_guardrails(safety_res)
        
        return {
            "success": True,
            "summary": summary,
            "guardrails": guardrails
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
