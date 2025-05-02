# Workflows 

The idea of workflows is that browser-use can save a lot of time by caching agent runs in workflow files. Workflows are a mix of detemrinsitic and agentic actions that take place in succession. Workflows must be easy to define, easy to run, and robust. 
Workflows also save on costs, since they require less model calls that normal agent runs. 

- Use record tool to create this json files that can be cast to workflows.
- Use model to turn them into workflows with the correct kind of format and also with the AI interlaced when needed
- people can edit their workflows
# Long vision 
People create share and monetize on their workflows. Workflows can be create by looking at agent runs, can be create manually by specifying workflow files, can be created by registering human actions on a browser.

# Example applications 
1 - Send a message on linkedin to Gregor Zunic.
2 - Go to yahoo finance and give me the price of google stock right now.


### Examples
Working and non working workflows are in their relative folders

- whatsapp works
- slack does not work because of a tab switch, slack opens a new tab.
- forms are as painful to fill this way, plus the workflow is not great. I think a very cool thing to do would be to have the LLM also filling input for other tasks, for instance, in the current format to fill a form automatically I need to basically fill another format, suppose for instance instead I wanted to send a document or something like this. MY MCP mind tells me that this could be done by transforming the workflow into a tool and having an LLM calling the workflow with the desired arguments. 
- linkedin accept invitation if certain condition

Multi Selector: 
 - pierce
 - aria
 - xpath
 - css selector



 # TODO
 - [] The recorder records each key press input when inputting a text, i.e. it is not debounced, and for each one we save a screenshot. For now in workflow_builder I will discard those screnshot as they do not add value (just one more letter) but they make the api call expensive and slow af