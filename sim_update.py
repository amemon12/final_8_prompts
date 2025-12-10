import boto3
from botocore.exceptions import ClientError
import json
from typing import Dict, List, Optional
from datetime import datetime


def flatten_sims_for_llm(sims_data: Dict) -> List[Dict]:
    """
    Flattens the hierarchical SIM structure into a list of facts for LLM processing.
    
    Args:
        sims_data: The full SIM JSON structure with categories
    
    Returns:
        List of all facts from all categories
    """
    all_facts = []
    
    for category, category_data in sims_data.items():
        if isinstance(category_data, dict) and "Facts" in category_data:
            facts = category_data["Facts"]
            if isinstance(facts, list):
                all_facts.extend(facts)
    
    return all_facts


def update_user_sims(user_query: str, existing_sims: List[Dict]) -> Dict:
    """
    Analyzes user query with all existing sims and returns what action to take (add/update/both/nothing).
    
    Args:
        user_query: The user's input message
        existing_sims: List of existing fact dictionaries from all categories
    
    Returns:
        Dict with one of these formats:
        - {"action": "add", "additions": [{"fact_id": "...", "fact": "..."}]}
        - {"action": "update", "updates": [{"fact_id": "...", "fact": "..."}]}
        - {"action": "both", "updates": [...], "additions": [...]}
        - {"action": "nothing"}
    """
    
    # Create an Amazon Bedrock Runtime client
    brt = boto3.client("bedrock-runtime")
    
    # Set the model ID for Mistral
    model_id = "mistral.mistral-large-2402-v1:0"
    
    # Format existing sims for the prompt
    existing_sims_text = json.dumps(existing_sims, indent=2) if existing_sims else "[]"
    
    # Create the sim update prompt - NOTE: All JSON examples use {{ }} to escape braces
    system_message = """SYSTEM:
You are a highly reliable assistant specialized in managing personalized user information stored in a structured format.
Follow all instructions exactly and produce structured, correct, and concise outputs.

TASK DESCRIPTION:
Analyze the user's query to determine if it contains information that should UPDATE existing personal information, ADD new personal information, or requires NOTHING. You must decide:
(1) Does the query mention something already present in existing facts?
(2) If yes, does it provide MORE DETAIL or CONTRADICT existing info? → UPDATE
(3) If it's entirely new information → ADD
(4) If it's redundant or very similar to existing info → NOTHING
(5) If BOTH new and updated information exists → BOTH

CONTEXT:
User information is stored in a hierarchical JSON structure with categories (Travel, Family, Health, etc.), where each category contains:
- Description: Overview of the category
- Facts: Array of fact objects with id, fact (one sentence), and timestamps
- Credentials/Relationships: Additional structured data

Each fact is a single sentence describing a user preference, constraint, context, or characteristic.

DECISION LOGIC:
1. CHECK FOR OVERLAP:
   - Does the user's query mention a topic already covered in existing facts?
   - Look at the MEANING, not just exact words
   - Check across ALL categories for potential matches

2. IF OVERLAP EXISTS:
   - Does new info ADD MORE DETAIL? → include in updates
   - Does new info CONTRADICT? → include in updates
   - Is it REDUNDANT (same info, no new details)? → action: "nothing"

3. IF NO OVERLAP:
   - Create NEW fact → include in additions

4. IF BOTH:
   - Include both updates and additions in response

CONSTRAINTS:
- Return ONLY valid JSON with no additional text, explanations, or markdown
- Do NOT include timestamps in your response (system will add them automatically)
- Each fact must be ONE complete sentence
- When updating, MERGE the new information with existing content - don't overwrite
- Do NOT invent information not present in the user query
- Do NOT create duplicate facts for the same topic
- Be decisive and specific
- For updates, preserve all existing information while incorporating new details

EXPECTED OUTPUT FORMATS:

For ADD only (completely new information):
{{
  "action": "add",
  "additions": [
    {{
      "fact_id": "category_###",
      "fact": "Complete sentence describing the user's new preference/context."
    }}
  ]
}}

For UPDATE only (more detail or contradiction):
{{
  "action": "update",
  "updates": [
    {{
      "fact_id": "existing_fact_id",
      "fact": "Updated sentence that includes BOTH previous information AND new details, merged naturally."
    }}
  ]
}}

For BOTH ADD and UPDATE:
{{
  "action": "both",
  "updates": [
    {{
      "fact_id": "existing_fact_id_1",
      "fact": "Updated sentence with merged information."
    }},
    {{
      "fact_id": "existing_fact_id_2",
      "fact": "Another updated sentence with merged information."
    }}
  ],
  "additions": [
    {{
      "fact_id": "category_###",
      "fact": "New fact sentence."
    }},
    {{
      "fact_id": "category_###",
      "fact": "Another new fact sentence."
    }}
  ]
}}

For NOTHING (redundant or very similar):
{{
  "action": "nothing"
}}

IMPORTANT NOTES:
- When updating, always preserve the essence of the original fact while incorporating new information
- Use natural language to merge information (e.g., "previously X but now Y", "X and also Y", "X, which has changed to Y")
- For new fact_ids when adding, use the category prefix and increment from the highest existing number
- Never return timestamps - the system handles those automatically
- If multiple facts need updating or adding, include all in the respective arrays
- Prioritize clarity and completeness in the merged fact statements
- Action can be "add", "update", "both", or "nothing"

EXISTING SIMS:
{existing_sims}

USER QUERY:
{user_query}

Return ONLY the JSON response, no other text."""
    
    conversation = [
        {
            "role": "user",
            "content": [{"text": system_message.format(
                existing_sims=existing_sims_text,
                user_query=user_query
            )}],
        }
    ]
    
    try:
        # Send the message to Mistral
        response = brt.converse(
            modelId=model_id,
            messages=conversation,
            inferenceConfig={"maxTokens": 1000, "temperature": 0.2, "topP": 0.9},
        )
        
        # Extract the response text
        response_text = response["output"]["message"]["content"][0]["text"]
        
        # Parse the JSON response
        result = json.loads(response_text.strip())
        
        # Validate the response format
        action = result.get("action", "nothing")
        
        if action in ["add", "update", "both", "nothing"]:
            return result
        else:
            print(f"Warning: Invalid action '{action}', defaulting to 'nothing'")
            return {"action": "nothing"}
        
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse JSON from response: {response_text}")
        print(f"JSON Error: {e}")
        return {"action": "nothing"}
        
    except (ClientError, Exception) as e:
        print(f"ERROR: Can't invoke '{model_id}'. Reason: {e}")
        return {"action": "nothing"}


def get_category_from_fact_id(fact_id: str) -> str:
    """
    Extracts category name from fact_id (e.g., 'travel_001' -> 'Travel')
    """
    prefix = fact_id.split('_')[0]
    category_map = {
        'travel': 'Travel',
        'health': 'Health',
        'family': 'Family',
        'pet': 'Pets',
        'hobby': 'Hobbies',
        'work': 'Work',
        'financial': 'Financial',
        'education': 'Education',
        'lifestyle': 'Lifestyle',
        'social': 'Social',
        'personality': 'Personality',
        'values': 'Values',
        'preferences': 'Preferences'
    }
    return category_map.get(prefix, 'Lifestyle')  # Default to Lifestyle if unknown


def apply_sim_action(action_result: Dict, filepath: str = "sim.json") -> bool:
    """
    Applies the action returned by update_user_sims to the sim.json file.
    
    Args:
        action_result: The dict returned by update_user_sims
        filepath: Path to the sim.json file
        
    Returns:
        True if successful, False otherwise
    """
    action = action_result.get("action", "nothing")
    
    if action == "nothing":
        print("No changes to apply.")
        return True
    
    # Load current sims
    sims_data = load_sims_from_file(filepath)
    current_timestamp = datetime.utcnow().isoformat() + "Z"
    
    # Handle UPDATES
    if action in ["update", "both"]:
        updates = action_result.get("updates", [])
        for update in updates:
            fact_id = update["fact_id"]
            new_fact = update["fact"]
            
            # Find and update the fact
            updated = False
            for category, category_data in sims_data.items():
                if isinstance(category_data, dict) and "Facts" in category_data:
                    for i, fact_obj in enumerate(category_data["Facts"]):
                        if fact_obj.get("id") == fact_id:
                            # Append new timestamp to existing timestamps
                            existing_timestamps = fact_obj.get("timestamps", [])
                            existing_timestamps.append(current_timestamp)
                            
                            # Update the fact
                            sims_data[category]["Facts"][i] = {
                                "id": fact_id,
                                "fact": new_fact,
                                "timestamps": existing_timestamps
                            }
                            updated = True
                            print(f"✓ Updated fact: {fact_id}")
                            break
                if updated:
                    break
            
            if not updated:
                print(f"Warning: Could not find fact with id '{fact_id}'")
    
    # Handle ADDITIONS
    if action in ["add", "both"]:
        additions = action_result.get("additions", [])
        for addition in additions:
            fact_id = addition["fact_id"]
            new_fact = addition["fact"]
            
            # Determine which category this belongs to
            category = get_category_from_fact_id(fact_id)
            
            # Ensure category exists
            if category not in sims_data:
                sims_data[category] = {
                    "Description": f"User's {category.lower()} information",
                    "Facts": [],
                    "Credentials": {}
                }
            
            # Add the new fact
            new_fact_obj = {
                "id": fact_id,
                "fact": new_fact,
                "timestamps": [current_timestamp]
            }
            
            sims_data[category]["Facts"].append(new_fact_obj)
            print(f"✓ Added new fact: {fact_id} to category {category}")
    
    # Save the updated data
    save_sims_to_file(sims_data, filepath)
    return True


def load_sims_from_file(filepath: str = "sim.json") -> Dict:
    """
    Load existing sims from a JSON file.
    
    Args:
        filepath: Path to the sim.json file
        
    Returns:
        Dictionary with the full SIM structure
    """
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            
            if isinstance(data, dict):
                return data
            else:
                print(f"Warning: Unexpected format in {filepath}")
                return {}
                
    except FileNotFoundError:
        print(f"Warning: {filepath} not found. Creating new structure.")
        return {}
    except json.JSONDecodeError:
        print(f"Error: Could not parse {filepath}. Please check file format.")
        return {}


def save_sims_to_file(sims_data: Dict, filepath: str = "sim.json"):
    """
    Save sims to a JSON file.

    Args:
        sims_data: Full SIM dictionary to save
        filepath: Path to the sim.json file
    """
    try:
        with open(filepath, 'w') as f:
            json.dump(sims_data, f, indent=2)

        # Count total facts
        total_facts = sum(
            len(cat_data.get("Facts", []))
            for cat_data in sims_data.values()
            if isinstance(cat_data, dict)
        )
        print(f"✓ Saved {total_facts} facts across {len(sims_data)} categories to {filepath}")
    except Exception as e:
        print(f"Error saving to {filepath}: {e}")