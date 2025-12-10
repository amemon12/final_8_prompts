import boto3
from botocore.exceptions import ClientError
import json
from typing import Dict

def route_user_input(user_input: str) -> Dict[str, str]:
    """
    Routes user input to determine action type and similarity check needs.
    
    Returns:
        Dict with keys:
        - 'action': 'plan' or 'respond'
        - 'sim_update': 'y' or 'n'
    """
    
    # Create an Amazon Bedrock Runtime client
    brt = boto3.client("bedrock-runtime")
    
    # Set the model ID for Mistral
    model_id = "mistral.mistral-large-2402-v1:0"
    
    # Create the routing prompt with two classification tasks
    system_message  = """SYSTEM:
You are a highly reliable assistant specialized in travel query classification and routing.
Follow all instructions exactly and produce structured, correct, and concise outputs.

TASK DESCRIPTION:
Analyze the user's travel-related message and make TWO classification decisions: (1) Determine if the query contains NEW information about the user that should be stored/updated in their personalized profile (sim_update), and (2) Determine if the query requires creating a detailed travel plan (action: plan) or can be answered directly with information/recommendations (action: respond).

CONTEXT:
You will receive a user message related to travel. You must classify it along two dimensions:

ACTION CLASSIFICATION:
- "plan" → The user is requesting creation of a detailed travel plan, itinerary, or multi-step travel arrangement. This includes: multi-day schedules, coordinating flights/hotels/activities, comparing multiple destinations with planning intent, budget-based trip planning, route optimization, or comprehensive trip organization.
- "respond" → The user is asking a question that can be directly answered without creating a plan. This includes: single facts, quick recommendations, basic information, yes/no questions, general advice, or informational queries about travel topics.

UPDATE INFO CHECK (sim_update):
- "y" → The user's message contains NEW information about themselves that should be stored for future personalization. This includes: travel preferences, budget constraints, travel style, dietary restrictions, mobility limitations, interests/hobbies, home location, passport/citizenship, family/companion details, preferred airlines/hotels, dislikes/constraints, or any personal context that would help personalize future recommendations.
- "n" → The user is asking a general travel question without revealing any new personal information about themselves. Nothing new to store.

KEY DECISION LOGIC FOR sim_update:
- If user states preferences: "I love beaches" → sim_update: y
- If user mentions constraints: "I have a $2000 budget" → sim_update: y
- If user shares personal context: "I'm traveling with my elderly parents" → sim_update: y
- If user mentions home location: "I'm from Seattle" → sim_update: y
- If user states dislikes: "I don't like crowded places" → sim_update: y
- If user reveals interests: "I'm into photography" → sim_update: y
- If user asks general questions with no personal info: "What's the weather in Paris?" → sim_update: n
- If user asks for plans but provides personal details: "Plan a trip, I love adventure sports" → sim_update: y

CONSTRAINTS:
- Return ONLY valid JSON with no additional text, explanations, or markdown
- Use exactly this format: {"action": "plan", "sim_update": "y"}
- action must be either "plan" or "respond"
- sim_update must be either "y" or "n"
- Do NOT invent information not present in the user query
- Be decisive - choose the most appropriate classification based on the user's explicit content
- Focus on NEW information the user is sharing, not what they're asking

EXPECTED OUTPUT:
A single JSON object with two keys:
{
  "action": "plan" or "respond",
  "sim_update": "y" or "n"
}

EXAMPLES:
User: "What's the weather in Paris?" 
Output: {"action": "respond", "sim_update": "n"}
Reasoning: General question, no personal information shared.

User: "Plan a 5-day trip to Paris for me"
Output: {"action": "plan", "sim_update": "n"}
Reasoning: Requesting plan creation but no personal preferences/constraints mentioned.

User: "Best time to visit Japan?"
Output: {"action": "respond", "sim_update": "n"}
Reasoning: General informational question, no personal info.

User: "Help me plan a 2-week Japan itinerary, I love history and temples"
Output: {"action": "plan", "sim_update": "y"}
Reasoning: Requesting plan + reveals personal interest in history/temples.

User: "Do I need a visa for Thailand? I'm a Canadian citizen"
Output: {"action": "respond", "sim_update": "y"}
Reasoning: Factual question but reveals citizenship information.

User: "I have a $3000 budget and want to visit Greece"
Output: {"action": "plan", "sim_update": "y"}
Reasoning: Planning request + budget constraint and destination preference shared.

User: "What are the best hotels in Tokyo?"
Output: {"action": "respond", "sim_update": "n"}
Reasoning: General recommendation request, no personal details.

User: "I'm vegetarian and want to know about food options in India"
Output: {"action": "respond", "sim_update": "y"}
Reasoning: Informational query but reveals dietary restriction.

User: "Show me my Italy trip plan"
Output: {"action": "respond", "sim_update": "n"}
Reasoning: Retrieving existing plan, no new personal info.

User: "I have 5 days off and love beaches, where should I go?"
Output: {"action": "plan", "sim_update": "y"}
Reasoning: Planning query + reveals time constraint and beach preference.


"""
    
    conversation = [
        {
            "role": "user",
            "content": [{"text": f"{system_message}\n\nUser message: {user_input}"}],
        }
    ]
    
    try:
        # Send the message to Mistral
        response = brt.converse(
            modelId=model_id,
            messages=conversation,
            inferenceConfig={"maxTokens": 100, "temperature": 0.1, "topP": 0.9},
        )
        
        # Extract the response text
        response_text = response["output"]["message"]["content"][0]["text"]
        
        # Parse the JSON response
        result = json.loads(response_text.strip())
        
        # Extract and validate action
        action = result.get("action", "respond")
        if action not in ["plan", "respond"]:
            print(f"Warning: Invalid action '{action}', defaulting to 'respond'")
            action = "respond"
        
        # Extract and validate sim_update
        sim_update = result.get("sim_update", "n")
        if sim_update not in ["y", "n"]:
            print(f"Warning: Invalid sim_update '{sim_update}', defaulting to 'n'")
            sim_update = "n"
            
        return {
            "action": action,
            "sim_update": sim_update
        }
        
    except json.JSONDecodeError:
        print(f"ERROR: Could not parse JSON from response: {response_text}")
        return {"action": "respond", "sim_update": "n"}  # Default values on error
        
    except (ClientError, Exception) as e:
        print(f"ERROR: Can't invoke '{model_id}'. Reason: {e}")
        return {"action": "respond", "sim_update": "n"}  # Default values on error