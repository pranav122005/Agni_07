import os
from groq import Groq

# Set your API key
# export GROQ_API_KEY="your_key_here"

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """
You are an AI Road Emergency Helpline Agent.
Your job is to:
- Calm the user
- Understand road emergencies (accidents, breakdowns, tyre burst, engine failure)
- Ask minimal clarification questions if needed
- Give clear instructions
- Inform that help is being dispatched to NHAI / emergency services
Keep responses short, reassuring, and authoritative.
"""

def get_ai_response(user_query: str) -> str:
    completion = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_query}
        ],
        temperature=0.4,
        max_tokens=200
    )

    return completion.choices[0].message.content
