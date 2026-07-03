import asyncio
from server import RxPlainHandler
import json

async def run_test():
    prescription = """Simvastatin 20mg 1 tab po qd
Clarithromycin 500mg 1 tab po bid
Amlodipine 5mg 1 tab po od
Lisinopril 10mg 1 tab po qd"""

    class DummyHandler:
        pass
    
    # We dynamically attach run_pipeline to our DummyHandler
    # Since run_pipeline doesn't use self except to call other static-like things, this works.
    from server import RxPlainHandler
    h = DummyHandler()
    h.run_pipeline = RxPlainHandler.run_pipeline.__get__(h)
    
    result = await h.run_pipeline(prescription, "")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(run_test())
