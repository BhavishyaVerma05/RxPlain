import os
from groq import Groq

def main():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("No API key")
        return
        
    client = Groq(api_key=api_key)
    models = client.models.list()
    for m in models.data:
        if "vision" in m.id.lower():
            print(m.id)

if __name__ == "__main__":
    main()
