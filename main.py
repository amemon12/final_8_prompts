import asyncio
from router import route_user_input
from sim_update import update_user_sims, load_sims_from_file
from respond import response
from correct_sim_plan import sim_plan, fetch_relevant_categories
from mcp_connected import plan
from rag_sim import get_top3_relevant_sims


async def main():
    user_query = input("Enter user query: ")

    output_router=route_user_input(user_query)
    output_sim_update=output_router.get("sim_update")
    output_action= output_router.get("action")

    if(output_sim_update=='y'):
        existing_sims=load_sims_from_file("sim.json")
        update_user_sims(user_query,existing_sims)

    if(output_action == 'respond'):
        relevant_sims=get_top3_relevant_sims(user_query,"sim.json")
        print(response(user_query,relevant_sims))
    else:
        correct_sims=sim_plan(user_query,"sim.json")
        relevant_categories= correct_sims.get("relevant_categories")
        print(relevant_categories)
        sim_data=fetch_relevant_categories(relevant_categories,"sim.json")
        print(sim_data)
        prev_json= {
                "task_summary": "",
                "followup_required": True,
                "action": "",
                "followups": [],
                "answer":""
        }

        output_json=await plan(user_query,sim_data,prev_json)
        followup_req=output_json.get("followup_required")
        while(followup_req):
            followups = output_json.get("followups", [])
            for followup in followups:
                print(followup.get("question"))
            user_answer=input("Answer followup question:> ")
            output_json=await plan(user_answer,sim_data,output_json)
            followup_req=output_json.get("followup_required")

        print(output_json.get("answers"))


if __name__ == "__main__":
    asyncio.run(main())

    



        
       



    

    





