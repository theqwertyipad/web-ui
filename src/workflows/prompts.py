# -----------------------------------------------------------------------------
# Prompt template for converting raw recorder *events* into an executable
# **JSON workflow** definition.
# -----------------------------------------------------------------------------

workflow_builder_template = """\
You are a senior software engineer working with the *browser-use* open-source library.
Your task is to convert a JSON recording of browser events (shown below) into an
*executable JSON workflow* that the runtime can consume **directly**.

Follow these rules when generating the output JSON:
1. Top-level keys (in order): \"name\", \"description\", \"input_schema\" (optional), \"steps\" and \"version\".
   • \"input_schema\" – if present – MUST follow JSON-Schema draft-7 subset semantics:
       {{
         \"type\": \"object\", 
         \"properties\": {{ \"foo\": {{\"type\": \"string\"}}, … }},
         \"required\": [\"foo\", …]
       }}
   • Omit \"inputs\" entirely if the workflow is fully deterministic and requires
     no external parameters.
2. \"steps\" is an array of dictionaries executed sequentially.
   • Each dictionary MUST include a ``\"type\"`` field.
   • **Agent events** → ``\"type\": \"agent\"`` **MUST** also include a ``\"task\"``
     string that clearly explains what the agent should achieve **from the
     user's point of view**.  A short ``\"description\"`` of *why* the step
     requires agent reasoning is encouraged, plus an optional ``\"max_steps\"``
     integer (defaults to 5 if omitted).
   • **Deterministic events** → keep the original recorder event structure.  The
     value of ``\"type\"`` MUST match **exactly** one of the available action
     names listed below; all additional keys are interpreted as parameters for
     that action.
   • For each step you create also add a description that describes what the step tries to achieve.  
3. When referencing workflow inputs inside event parameters or agent tasks use
   the placeholder syntax ``{{input_name}}`` (e.g. \"cssSelector\": \"#msg-{{row}}\")
   – do *not* use any prefix like \"input.\". Decide the inputs dynamically based on the user's
   goal.
4. Quote all placeholder values to ensure the JSON parser treats them as
   strings.
5. In the events you will find all the selectors relative to a particular action, replicate all of them in the workflow.


High-level task description provided by the user (may be empty):
{goal}

Available actions:
{actions}

JSON session events to convert:
{events}
"""
