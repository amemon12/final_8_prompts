import boto3
from botocore.exceptions import ClientError
import json
from typing import Dict, List, Any

def fetch_relevant_categories(category_names, sims_file_path="sim.json"):
    """
    Fetch the actual category data from sim.json based on category names.

    Args:
        category_names: List of category names to fetch
        sims_file_path: Path to the sim.json file

    Returns:
        Dictionary containing only the relevant categories and their data
    """
    with open(sims_file_path, 'r') as f:
        all_sims = json.load(f)

    relevant_data = {}
    for category in category_names:
        if category in all_sims:
            relevant_data[category] = all_sims[category]

    return relevant_data


def sim_plan(query, sims_file_path: str="sim.json"):
    brt = boto3.client("bedrock-runtime")

    model_id = "meta.llama3-1-8b-instruct-v1:0"
    with open(sims_file_path, 'r') as f:
        sims_data = json.load(f)
    
    user_characteristics = sims_data.get('user_characteristics', {})
    print(f"Fetched {len(user_characteristics)} category/categories")
    
    # Build complete user profile with all facts
    user_profile_str = json.dumps(user_characteristics, indent=2)
    
    # Dynamically extract available categories and their descriptions for quick reference
    available_categories = []
    for category_name, category_data in user_characteristics.items():
        description = category_data.get('Description', 'No description available')
        num_facts = len(category_data.get('Facts', []))
        available_categories.append(f"- {category_name}: {description} ({num_facts} facts)")
    
    available_categories_str = "\n".join(available_categories)
    
    system_message = """You are a characteristic extraction AI that analyzes user queries and identifies the most relevant user characteristic CATEGORIES needed to provide personalized responses.

TASK:
Extract the top 5 most relevant user characteristic CATEGORIES from the available profile data that are needed to answer the user's query accurately and personally.

INPUT FORMAT:
You will receive user profile data structured as a JSON object with categories as keys. Each category contains:
- Description: What the category covers
- Facts: Array of specific user facts with id, fact text, and timestamps

EXAMPLE INPUT STRUCTURE:
{{
  "Travel": {{
    "Description": "User's travel experiences, preferences, constraints, and planning behaviors",
    "Facts": [
      {{"id": "travel_001", "fact": "The user prefers flying with Delta due to better rewards program benefits.", "timestamps": ["2023-03-15T09:00:00Z"]}},
      {{"id": "travel_002", "fact": "The user favors boutique hotels over large chain hotels.", "timestamps": ["2023-03-20T18:30:00Z"]}}
    ]
  }},
  "Health": {{
    "Description": "User's health conditions, fitness routines, dietary practices, and wellness habits",
    "Facts": [
      {{"id": "health_001", "fact": "The user has type 2 diabetes and monitors blood sugar regularly.", "timestamps": ["2023-01-15T08:00:00Z"]}},
      {{"id": "health_002", "fact": "The user is training for a triathlon.", "timestamps": ["2024-01-05T06:30:00Z"]}}
    ]
  }},
  "Personality": {{
    "Description": "User's personality traits, behavioral patterns, and cognitive preferences",
    "Facts": [
      {{"id": "personality_001", "fact": "The user has ADHD and uses Pomodoro technique.", "timestamps": ["2023-01-15T09:00:00Z"]}},
      {{"id": "personality_002", "fact": "The user is analytical and creates pro-con lists.", "timestamps": ["2023-02-18T19:00:00Z"]}}
    ]
  }}
}}

INSTRUCTIONS:
1. Read the user's query carefully
2. Review the COMPLETE USER PROFILE DATA below to understand all available facts
3. Identify which CATEGORIES contain facts most relevant to answering the query
4. Prioritize categories that directly impact the answer
5. Return exactly 5 category names in order of relevance (most relevant first)
6. Output ONLY a valid JSON object, nothing else

AVAILABLE CATEGORIES SUMMARY:
{available_categories}

COMPLETE USER PROFILE DATA (ALL FACTS):
{user_profile}

EXAMPLES:

Example 1:
User Query: "I want to plan a family vacation. What are some good travel options?"

Expected Output:
{{
  "relevant_categories": [
    "Travel",
    "Family",
    "Health",
    "Personality",
    "Financial"
  ],
  "reasoning": "Travel category contains destination preferences and constraints; Family category affects who's traveling and planning considerations; Health category includes mobility and heat sensitivity constraints; Personality category includes climate preferences; Financial category determines budget constraints."
}}

Example 2:
User Query: "Can you recommend a workout routine for me?"

Expected Output:
{{
  "relevant_categories": [
    "Health",
    "Lifestyle",
    "Personality",
    "Pets",
    "Work"
  ],
  "reasoning": "Health category contains current training goals and medical conditions; Lifestyle category affects available time and energy levels; Personality category impacts routine structure needs; Pets category constrains workout timing; Work category affects schedule availability."
}}

Example 3:
User Query: "What should I cook for dinner tonight?"

Expected Output:
{{
  "relevant_categories": [
    "Health",
    "Family",
    "Lifestyle",
    "Values",
    "Hobbies"
  ],
  "reasoning": "Health category determines dietary restrictions and timing; Family category indicates cooking for multiple people; Lifestyle category includes meal prep habits; Values category influences ingredient sourcing; Hobbies category may include cooking interests."
}}

Example 4:
User Query: "I need to organize my work schedule better. Any suggestions?"

Expected Output:
{{
  "relevant_categories": [
    "Work",
    "Personality",
    "Lifestyle",
    "Pets",
    "Family"
  ],
  "reasoning": "Work category contains role requirements and preferences; Personality category affects productivity techniques and timing; Lifestyle category indicates energy patterns; Pets category creates fixed commitments; Family category impacts availability."
}}

Example 5:
User Query: "I'm feeling overwhelmed and stressed. What should I do?"

Expected Output:
{{
  "relevant_categories": [
    "Personality",
    "Values",
    "Lifestyle",
    "Family",
    "Social"
  ],
  "reasoning": "Personality category contains stress coping mechanisms; Values category includes meditation practices; Lifestyle category reveals sleep issues contributing to stress; Family category indicates care responsibilities; Social category shows need for alone time."
}}

CRITICAL: Your output must be ONLY valid JSON in the exact format shown above with:
- "relevant_categories": an array of exactly 5 category names (strings)
- "reasoning": a single string explaining the relevance

Now analyze the following:

USER QUERY:
{user_query}

Return ONLY the JSON response, no other text."""
    
    conversation = [
        {
            "role": "user",
            "content": [{"text": system_message.format(
                available_categories=available_categories_str,
                user_profile=user_profile_str,
                user_query=query
            )}],
        }
    ]

    try:
        response = brt.converse(
            modelId=model_id,
            messages=conversation,
            inferenceConfig={"maxTokens": 512, "temperature": 0.5, "topP": 0.9},
        )

        response_text = response["output"]["message"]["content"][0]["text"]
        # Parse the JSON response before returning
        parsed_response = json.loads(response_text)
        return parsed_response

    except (ClientError, Exception) as e:
        return(f"ERROR: Can't invoke '{model_id}'. Reason: {e}")