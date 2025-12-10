import json
from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_aws import BedrockEmbeddings


def get_top3_relevant_sims(user_query: str, sims_file_path: str = "sim.json", aws_region: str = "us-east-1") -> List[Dict[str, Any]]:
    """
    Fetch sims from sim.json, run RAG, and output top 3 similar sims.
    
    Args:
        user_query: The user's search query
        sims_file_path: Path to the sim.json file
        aws_region: AWS region for Bedrock
    
    Returns:
        List of top 3 most relevant complete sim objects with similarity scores
    """
    
    print(f"Fetching sims from {sims_file_path}...")
    with open(sims_file_path, 'r') as f:
        sims_data = json.load(f)

    # Handle the hierarchical structure: categories -> facts
    documents = []
    fact_index = 0

    for category_name, category_data in sims_data.items():
        if isinstance(category_data, dict) and "Facts" in category_data:
            facts = category_data.get("Facts", [])

            for fact_obj in facts:
                fact_id = fact_obj.get("id", "")
                fact_text = fact_obj.get("fact", "")

                # Create searchable text combining category and fact
                text = f"{category_name}: {fact_text}"

                documents.append(Document(
                    page_content=text,
                    metadata={
                        "fact_index": fact_index,
                        "category": category_name,
                        "fact_id": fact_id,
                        "original_fact_json": json.dumps(fact_obj)
                    }
                ))
                fact_index += 1

    print(f"Fetched {len(documents)} facts from {len(sims_data)} categories")

    # Handle empty documents case
    if not documents:
        print("Warning: No facts found in sim.json")
        return []
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )
    splits = text_splitter.split_documents(documents)
    
    
    embeddings = BedrockEmbeddings(
        model_id="amazon.titan-embed-text-v2:0",
        region_name=aws_region
    )
    
    vectorstore = Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
        collection_name="sims_rag"
    )
    
    print(f"Running RAG with query: '{user_query}'")
    results = vectorstore.similarity_search_with_score(user_query, k=3)

    top3_facts = []
    seen_fact_ids = set()

    for doc, score in results:
        # Safely access metadata with .get() to handle splits
        fact_id = doc.metadata.get('fact_id', '')

        if not fact_id:
            # Skip if metadata is missing
            continue

        # Avoid duplicates
        if fact_id in seen_fact_ids:
            continue

        seen_fact_ids.add(fact_id)

        original_fact_json = doc.metadata.get('original_fact_json', '{}')
        original_fact = json.loads(original_fact_json)

        top3_facts.append({
            "rank": len(top3_facts) + 1,
            "category": doc.metadata.get('category', 'Unknown'),
            "fact_id": fact_id,
            "fact": original_fact,
            "similarity_score": float(score)
        })

        if len(top3_facts) == 3:
            break

    return top3_facts
