import asyncio
import os
import json
import re
import logging
from dotenv import load_dotenv
from langchain_aws import ChatBedrock
from mcp_use import MCPAgent, MCPClient
from prompt_assitant import prompt_assistant
import boto3

# Suppress mcp_use logging
logging.getLogger("mcp_use").setLevel(logging.WARNING)
logging.getLogger("mcp_use.telemetry.telemetry").setLevel(logging.WARNING)


async def plan(user_input, relevant_sims, prev_json):
   
    # Load environment variables
    load_dotenv()
    
    # AWS Bedrock setup
    region = os.getenv("AWS_REGION", "us-west-2")
    
    # Create Bedrock Runtime client
    brt = boto3.client(
        "bedrock-runtime",
        region_name=region,
    )
    
    # Use inference profile ARN instead of model ID for Llama 3.3 70B
    model_id = "us.meta.llama3-3-70b-instruct-v1:0"  # Regional inference profile
    
    # Format the system message with prev_json and relevant_sims
    system_message = f"""{prompt_assistant}

Current State (prev_json): {json.dumps(prev_json, indent=2)}
User Characteristics (relevant_sims): {json.dumps(relevant_sims, indent=2)}
"""
    
    config_file = "mcp.json"

    # Suppress stderr from MCP server processes
    import sys

    # Redirect stderr to devnull while creating client
    with open(os.devnull, 'w') as devnull:
        old_stderr = sys.stderr
        sys.stderr = devnull
        try:
            client = MCPClient.from_config_file(config_file)
        finally:
            sys.stderr = old_stderr
    
    # Create LLM using ChatBedrock
    llm = ChatBedrock(
        model_id=model_id,
        client=brt,
        region_name=region,
        model_kwargs={
            "temperature": 0.7,
            "max_gen_len": 2048,
            "top_p": 0.9,
        }
    )
    
    agent = MCPAgent(
        llm=llm,
        client=client,
        max_steps=30,
        memory_enabled=True,
        system_prompt=system_message,             
    )
    
    response_json = None
    
    try:

        try:
            response = await agent.run(user_input)
            
            try:
                # If response is already a dict
                if isinstance(response, dict):
                    response_json = response
                # If response is a string, try to parse it
                elif isinstance(response, str):
                    # Remove markdown code blocks
                    cleaned_response = response.strip()
                    
                    # Remove ```json and ``` markers
                    cleaned_response = re.sub(r'^```json\s*', '', cleaned_response)
                    cleaned_response = re.sub(r'^```\s*', '', cleaned_response)
                    cleaned_response = re.sub(r'\s*```$', '', cleaned_response)
                    cleaned_response = cleaned_response.strip()
                    
                    # Try to parse the cleaned JSON with strict=False to allow control characters
                    response_json = json.loads(cleaned_response, strict=False)
                    
            except (json.JSONDecodeError, ValueError) as je:
                print(f"\n⚠️ JSON parsing error: {je}")
                try:
                    # Extract JSON more aggressively
                    json_match = re.search(r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}', response, re.DOTALL)
                    if json_match:
                        json_str = json_match.group()
                        # Clean markdown from extracted JSON
                        json_str = re.sub(r'```json\s*', '', json_str)
                        json_str = re.sub(r'```\s*', '', json_str)
                        json_str = json_str.strip()
                        
                        # Parse with strict=False
                        response_json = json.loads(json_str, strict=False)
                    else:
                        raise Exception("No JSON object found in response")
                        
                except Exception as e:
                    print(f"\n⚠️ Fallback parsing failed: {e}")
                    # Last resort: save raw response for debugging
                    print(f"\n🔍 Raw response (first 500 chars):\n")
                    response_json = {
                        "task_summary": "Error parsing response - check raw output above",
                        "followup_required": False,
                        "action": "error",
                        "followups": [],
                        "raw_response": str(response)
                    }
                
        except Exception as e:
            print(f"\n❌ Error: {e}")
            if os.getenv("DEBUG", "false").lower() == "true":
                import traceback
                traceback.print_exc()
            
            response_json = {
                "task_summary": f"Error: {str(e)}",
                "followup_required": False,
                "action": "error",
                "followups": []
            }
    
    finally:
        if client and client.sessions:
            await client.close_all_sessions()
        print("✅ Done!")
    
    return response_json  # RETURN the JSON response