workflow_builder_template = """
		You are a senior software engineer working with the *browser-use* open-source
		library. Your task is to convert a JSON recording of browser events (shown
		below) into a valid *workflow* YAML file that *browser-use* can execute.

		The YAML must follow these rules:
		• Include the following top-level keys in this order: ``name``, ``description``, ``inputs`` , ``steps``.
		• ``inputs`` must follow the same JSON-schema-like structure used in the example (``type: object``, ``properties``, ``required`` list).
		• ``steps`` – a list of dictionaries executed sequentially.
		    Each step MUST contain a ``type`` and ``description``.
		    The ``type`` field MUST be either ``deterministic`` or ``agent``. No other values are permitted.

		    For most steps, use deterministic type:
		        type: deterministic
		        description: <description of the step>
		        action: <one of the available actions listed further below>
		        params: <mapping of parameters for that action> (can be empty)
		               IMPORTANT:
		               • Parameter names MUST EXACTLY match the field names defined in the action's
		                 input model class (e.g., use "url" for go_to_url, "selector" for
		                 click_element_by_css_selector, "text" for input_text, etc.).  Invalid
		                 parameter names will cause the workflow to fail.
		               • When you need to reference one of the workflow *inputs* inside a parameter
		                 value (or inside an agent task), use Python-format placeholders of the form
		                 ``{{input_name}}`` **without** any ``input.`` prefix.  For example:
		                     text: "{{contact_name}}"
		                 Here ``contact_name`` must exactly match the key declared under
		                 ``inputs.properties``.  Do *not* generate variants like ``{{input.contact_name}}`` –
		                 they will not resolve at runtime.
		               • Quote placeholder values in YAML strings to prevent the YAML parser from
		                 interpreting them as inline objects (e.g., use ``text: "{{email}}"``).
		            
		    Only use agent type when absolutely necessary (e.g. complex decision making or custom text input):
		        type: agent
		        description: <description of the step>
		        task: <description of what the agent should accomplish>
		              Can include {{input}} placeholders from workflow inputs.
		        max_steps: <optional maximum number of attempts>
		            
		• If a deterministic step fails, the agent will automatically take over.
		• Only use agent steps when the action requires:
		    - Complex decision making (e.g., choosing between multiple similar elements)
		    - Handling highly dynamic/variable UI states
		    - Complex conditional logic that can't be handled deterministically
            - Custom text input (e.g., entering a dynamic name, email, or message)
		• Do NOT invent actions – only use the ones provided below.
		• **Selector Preference:** Strongly prefer using CSS selectors (via actions like ``click_element_by_css_selector``, ``input_text_by_css_selector``, etc.) whenever an element needs targeting. CSS selectors are generally more concise and readable. Only use XPath selectors when CSS is not feasible.
		• **Index Parameter:** Do *not* use actions that require an ``index`` parameter (like ``input_text`` which takes an index), as index information is not available from the input events. Use specific targeters like CSS selectors or role/name instead.
		• Prefer ``go_to_url`` for navigation events.
		• Ignore browser events that cannot be reliably mapped to an available action.
		• Output ONLY the generated YAML content – no surrounding text, comments, or markdown fences (```).
		• Always start the workflow by creating a new browser tab so that the user's existing tabs are not disrupted.

		High-level task description provided by the user (may be empty):
		{goal}

		Available actions:
		{actions}

		JSON session events to convert:
		{events}
		"""
