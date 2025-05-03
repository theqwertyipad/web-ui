# -----------------------------------------------------------------------------
# Prompt template for converting raw recorder *events* into an executable
# **JSON workflow** definition.
# -----------------------------------------------------------------------------

# NOTE: The runtime engine can now consume recorder logs directly.  Therefore the
# LLM no longer needs to generate a YAML wrapper – instead it should output an
# *augmented* JSON specification that is a **superset** of the original
# recording:
#
#   {
#     "name": "Meaningful Workflow Name",
#     "description": "High-level summary …",
#     "inputs": { … optional JSON-Schema style definition … },
#     "events": [ <list of deterministic/agent events> ]
#   }
#
# The "events" array MUST preserve chronological order.  Each element maps
# 1-to-1 to a concrete controller *action* so that the engine can replay it
# deterministically.  Complex or ambiguous UI interactions that cannot be
# expressed deterministically **must** be replaced with an *agent* event of the
# form:
#
#   {
#     "type": "agent",
#     "description": "Why the agent is needed",
#     "task": "Natural-language instructions for the agent that may reference {{input}} placeholders",
#     "max_steps": 5
#   }
#
# Deterministic events follow the schema of their corresponding action model and
# therefore inherit the *exact* parameter names (see "Available actions" below).
#
# IMPORTANT CONSTRAINTS
# • Parameter names MUST EXACTLY match the field names defined in the action's
#   *param_model* (case-sensitive).  Invalid names will crash the workflow.
# • When referencing *workflow inputs* inside strings use Python-format
#   placeholders **without** the "input." prefix, e.g.:
#       "url": "https://example.com/?q={{search_term}}"
# • Do NOT generate actions that are not present in the "Available actions"
#   list.
# • **Selector preference:** favour CSS selectors.  Use XPath only if strictly
#   necessary.
# • Avoid actions that rely on an "index" parameter – the recorder does not
#   provide stable indices.
# • Always begin the workflow with a "new_tab" action so that the user's current
#   browsing session is not disturbed.  If the action list does not provide a
#   dedicated "new_tab" action, use the appropriate navigation action to open a
#   blank page.
# • Ignore recorder events that cannot be mapped reliably to an action (e.g.
#   mouse-move, resize events, etc.).
# • Output ONLY the final JSON – no markdown fences, comments, or prose.
#
# -----------------------------------------------------------------------------
workflow_builder_template = """\
You are a senior software engineer working with the *browser-use* open-source library.
Your task is to convert a JSON recording of browser events (shown below) into an
*executable JSON workflow* that the runtime can consume **directly**.

Follow these rules when generating the output JSON:
1. Top-level keys (in order): \"name\", \"description\", \"inputs\" (optional), \"events\".
   • \"inputs\" – if present – MUST follow JSON-Schema draft-7 subset semantics:
       {{
         \"type\": \"object\", 
         \"properties\": {{ \"foo\": {{\"type\": \"string\"}}, … }},
         \"required\": [\"foo\", …]
       }}
   • Omit \"inputs\" entirely if the workflow is fully deterministic and requires
     no external parameters.
2. \"events\" is an array of dictionaries executed sequentially.
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
3. When referencing workflow inputs inside event parameters or agent tasks use
   the placeholder syntax ``{{{{input_name}}}}`` (e.g. \"cssSelector\": \"#msg-{{{{row}}}}\")
   – do *not* use any prefix like \"input.\".
4. Quote all placeholder values to ensure the JSON parser treats them as
   strings.

High-level task description provided by the user (may be empty):
{goal}

Available actions:
{actions}

JSON session events to convert:
{events}
"""
