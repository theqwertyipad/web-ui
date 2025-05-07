from langchain_openai import ChatOpenAI
from src.workflows.workflow_builder import parse_session
workflow = parse_session(
    llm=ChatOpenAI(model="gpt-4o", temperature=0),
    session_path="whatsappmessage2.json",
    user_goal="I want to automatically send a message on whatsapp given the recipient name and the message, do it deterministically wihotu using he agent",
    use_screenshots=False,
)
print(workflow.json_path)
