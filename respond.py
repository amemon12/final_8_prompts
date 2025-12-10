import boto3
from botocore.exceptions import ClientError

def response(query, sim):
    brt = boto3.client("bedrock-runtime")


    model_id = "meta.llama3-1-8b-instruct-v1:0"


    system_message = """You are a personal AI assistant. Use the user's profile information to provide relevant, personalized answers.
    (Use USer Profile only if u feel the answer requires it)

    User Profile:
    {existing_sims}

    User's Question: {user_query}

    Answer , incorporating relevant details from their profile IF YOU FEEL THE ANSWER REQUIRES IT. DO ONLY WHAT YOU ARE ASKED FOR """
    
    conversation = [
        {
            "role": "user",
            "content": [{"text": system_message.format(
                existing_sims=sim,
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
        return(response_text)


    except (ClientError, Exception) as e:
        return(f"ERROR: Can't invoke '{model_id}'. Reason: {e}")
        