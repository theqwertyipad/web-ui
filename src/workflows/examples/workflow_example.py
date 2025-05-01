import asyncio

from langchain_openai import ChatOpenAI  # or any other provider compatible with langchain_core

from browser_use.workflows.workflow import Workflow


async def main():
	# Minimal LLM instantiation – replace with your own key / model name
	llm = ChatOpenAI(model='gpt-4o', temperature=0)  # Provide your model configuration via environment variables or defaults

	wf = Workflow(
		yaml_path='browser_use/workflows/linkedin_workflow.yaml',
		llm=llm,
	)

	inputs = {
		'email': 'pietro.zullo@gmail.com',
		'password': 'Larataya97$',
		'recipient': 'Alberto Carpentieri',
		'message': 'Ti sto mandando questi messaggi per testare una feature che sto costruend per browser use. In ogni caso sentiamoci per telefono se hai tempo piu tardi. Ciao!',
	}

	results = await wf.run_async(inputs=inputs)


if __name__ == '__main__':
	asyncio.run(main())
