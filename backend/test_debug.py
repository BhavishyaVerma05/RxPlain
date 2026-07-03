import asyncio
from mcp_server import get_safety_data

async def main():
    print("Testing get_safety_data for warfarin...")
    result = await get_safety_data("warfarin", ["amoxicillin", "acetaminophen", "pantoprazole"])
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
