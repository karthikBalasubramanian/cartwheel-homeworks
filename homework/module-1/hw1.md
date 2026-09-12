# Homework 1, implementing and examining the support agent

Homework 1 asks you to complete five tools for the Cartwheel support agent and examine the resulting behavior through manual conversations.

## Expected work

- Estimated time: 3 to 4.5 hours for a student who is comfortable with Python, or 4.5 to 6 hours for a student who is learning the repository and agent framework.
- Expected Python code: approximately 80 to 130 lines across five required functions in `agent/tools.py`, plus your own tools.
- Other work: at least 10 JSONL records, an analysis of one possible system prompt revision, and a video of no more than 5 minutes.

The estimates vary with the student's familiarity with Python and the model provider. The estimate includes time to explore the agent beyond the required cases, because Part C depends on observing how the model interprets the specification.

## Preparation

A [video walkthrough](https://youtu.be/qO98jDayTHo?si=gLN5FZ3FDiAIs_gG) of how to approach this assignment is available. Watch it before you begin for an overview of the expected workflow.

Run the assignment from the repository root. Install the Python environment and generate the local Cartwheel data:

```bash
uv sync
uv run python -m seed.generate
```

Copy `.env.example` to `.env` if `.env` does not already exist, then add the key for the model you will use during the manual session. The tests and seed command do not require a model key, but the command line chat does.

The seed command creates `data/cartwheel.db`, a local SQLite database containing the stores, products, users, orders, refunds, and escalations used by the assignment. The command also creates the policy documents under `data/policies/`. Generation is deterministic, so every student receives the same demonstration orders and policy facts. No external database service is required.

Confirm the generated files before implementing a tool:

```bash
ls data/cartwheel.db
ls data/policies
```

The starter contains the following components:

- `data/cartwheel.db` contains the stores, products, users, and orders used by the support application. The seed program generates the same records for every student.
- `agent/cli.py` provides a text interface for conversations with the support agent.
- `agent/auth.py` loads the selected user and provides the user's role to every tool.
- `agent/agent.py` contains three completed tools for help center search, order lookup, and refunds.
- `agent/tools.py` contains five unfinished tools for policy lookup, product search, order listing, cancellation, and fuzzy order search.
- `tests/test_hw_holes.py` contains one supplied contract test for each unfinished tool.

The agent has access only to the Cartwheel function tools registered in `TOOLS_BY_ROLE` in `agent/agent.py`. The agent does not receive a filesystem, shell, web, or file search tool. A model instruction is not an access control mechanism, so the order tools still check the authenticated user before returning private information.

Before editing the code, read the following files:

- `SPEC.md`, which defines the support agent's accepted requests, permissions, tool behavior, and escalation rules.
- `agent/auth.py`, which implements authorization by role.
- One completed tool function in `agent/agent.py`, which illustrates the tool result conventions.
- The docstring of each function marked for Homework 1.

The supplied data access layer in `agent/db.py` provides the database operations needed by the unfinished tools:

- `search_products` uses `get_store_by_name` and `list_products`.
- `list_my_orders` uses `list_orders_for_user` or `list_orders_for_store`.
- `cancel_order` uses `get_order` and `set_order_status`.
- `get_policy` reads the generated policy files with `load_policy_docs` from `agent/helpcenter.py`.
- `find_order` searches the authenticated user's orders by product name. Use `list_orders_for_user` and filter by matching the query against product names.

Use `with db.connection() as conn:` for database access. It closes the connection
automatically, including on early returns and errors:

```python
with db.connection() as conn:
    order = db.get_order(conn, order_id)
```

The supplied write helpers commit their changes. The `with` block only handles
closing; it does not commit pending writes. Existing code that uses `db.connect()`
and closes it explicitly still works. A bare `with db.connect()` does not close
a SQLite connection.

Use the supplied functions rather than writing a second database layer. Each tool docstring states the required inputs, return value, and error behavior.

`SPEC.md` is a design document; the running application does not load it. The starter translates the specification into three kinds of implementation:

- `SYSTEM_PROMPT_TEMPLATE` in `agent/agent.py` contains the scope, refusal, tool choice, citation, and escalation instructions needed by the model.
- `agent/auth.py` and the tool functions enforce permissions, because authorization cannot depend on whether the model follows an instruction.
- `facts.yaml`, `seed/eligibility.py`, and the refund tool enforce numerical policy rules, including the return period and approval threshold.

Homework 1 completes the missing tool contracts from the specification. During the manual session, compare the observed behavior with the specification. Part C asks you to revise the system prompt only when the missing behavior concerns a decision made by the model; a failure in authorization or state changes belongs in code.

## Part A, implement the five support tools

Implement the following functions in `agent/tools.py`:

- `get_policy`
- `search_products`
- `list_my_orders`
- `cancel_order`
- `find_order`

Follow the contract in each docstring, including its return schema and error behavior. For `cancel_order`, check whether the caller may access the order before returning any information about it. After authorization succeeds, check whether the shipment state permits cancellation.

`find_order` takes a natural language query (e.g., "earmuffs I bought last week") and searches the authenticated user's orders by product name. You may use a fuzzy string matching library such as `thefuzz` or `rapidfuzz`, or SQLite's `LIKE` operator for a simpler approach.

Run the focused tests while you work:

```bash
uv run pytest --runxfail tests/test_hw_holes.py -k hw1
```

The `--runxfail` option makes an unfinished function fail instead of appearing as an expected failure. Before you implement a function, its test should report a `NotImplementedError`. After you implement all five functions correctly, the command should report five passing tests.

During Part B conversations you will notice things the agent cannot do because no tool exists. Add more tools of your own to fill those gaps. Some ideas:

- Check whether an order is eligible for a return or refund
- Track shipment status and delivery dates
- Look up public store information and policy overrides
- Summarize a customer's recent order history

To add a tool, write a function decorated with `@function_tool` in `agent/tools.py` with a clear docstring (the SDK uses it as the tool description the model sees), then add it to `TOOLS_BY_ROLE` in `agent/agent.py` for the appropriate roles.

Then run the supplied tests for the completed tools, authorization rules, and refund rules:

```bash
uv run pytest tests/test_agent_tools.py tests/test_auth.py tests/test_eligibility.py
```

## Part B, examine the agent through manual conversations

Run at least 10 conversations with the completed support agent. Use all three authenticated roles, and save one record for each conversation.

Include every case in the following list:

- An authorized shopper request concerning order `4127`.
- A request concerning order `3980`, which is outside the refund window.
- A refund request for order `4455`, whose amount exceeds the automatic approval threshold.
- A merchant from store 2 requesting order `4127`, which belongs to store 1.
- A question whose answer depends on a policy override for one store.
- A request outside the support agent's stated scope.

The required order cases depend on permissions stored in the local database. Use shopper user `1` for orders `4127`, `3980`, and `4455`, because the shopper owns all three orders. Use merchant user `9002` for the request about order `4127`, because the merchant belongs to store 2 while the order belongs to store 1. Support user `9501` is available when you want to test the support role.

Use the command that matches the identity you want to test:

```bash
uv run python -m agent.cli --role shopper --user 1
uv run python -m agent.cli --role merchant --user 9002
uv run python -m agent.cli --role support --user 9501
```

The commands select the authenticated identity, but they do not determine the request.

Add `--debug` to print each tool call's name, arguments, and result after each
turn finishes. Use this output to fill in `tool_calls` in `hw1-session.jsonl`.
This works without Langfuse or the Homework 2 tracing setup. For example:

```bash
uv run python -m agent.cli --role shopper --user 1 --debug
```

Add four more conversations after reading `SPEC.md`. Here is the first case to add: as shopper user `1`, ask, "Can you change the email address on my Cartwheel account to new@example.com?" Determine the expected behavior from `SPEC.md`, then compare the expected behavior with the agent's response. Design the remaining three conversations yourself, including the role, user, and request for each conversation.

A refund or cancellation changes the local database. If you want to test another conversation against the original order state, run `uv run python -m seed.generate` before starting the next conversation. Keep the same database state throughout a conversation you are recording.

Write each conversation as one line of `hw1-session.jsonl`. Each record must contain:

- `role`, the authenticated role.
- `user_id`, the authenticated user's identifier.
- `store_id`, the authenticated merchant's store, or `null` for other roles.
- `request`, the user's request.
- `tool_calls`, a list containing each tool name, its arguments, and its result. Use an empty list when the agent called no tools.
- `response`, the agent's final response.
- `expected`, the behavior implied by the current specification.
- `requirement`, the identifier of the relevant requirement in `SPEC.md`, or `null` when no single requirement applies.
- `met_requirement`, `true` when the observed behavior met the requirement, and `false` when it did not.
- `problem_source`, either `prompt`, `tool`, `specification`, or `null`. Use `null` when the agent met the requirement.

Use `prompt` when the tools returned the right information but the model made a poor decision. Use `tool` when a function returned the wrong information or changed the wrong state. Use `specification` when `SPEC.md` does not say what correct behavior would be.

For example:

```json
{"role":"merchant","user_id":9002,"store_id":2,"request":"Show me order 4127.","tool_calls":[{"name":"get_order","arguments":{"order_id":4127},"result":{"ok":false,"error":"permission_denied"}}],"response":"I cannot provide information about the order.","expected":"The agent must not reveal information about an order from another store.","requirement":"AUTH-1","met_requirement":true,"problem_source":null}
```

## Part C, identify and test a missing model instruction

### 1. Analysis of System Prompt Misgivings vs. `SPEC.md`

Comparing `SPEC.md` with the starter `SYSTEM_PROMPT_TEMPLATE` in `agent/agent.py` reveals four key discrepancy patterns where the prompt was absent or expressed too vaguely:

* **Pattern 1: Non-Hallucination & Execution Verification (`RESP-2`, `RESP-3`)**
  * **Gap:** The starter prompt lacked instructions preventing the model from confirming an action (like a refund or cancellation) *before* tool execution returned `ok: true`. It also failed to instruct the model to state when data is missing or inconsistent (e.g., missing delivery date timestamps) rather than inventing dates.
* **Pattern 2: Missing Escalation Triggers (`ESC-2`, `ESC-3`) & Refund Seam Conflict (`ESC-1`)**
  * **Gap:** `ESC-2` mandates that non-payment account changes (email, shipping address) **must** escalate to a human (`escalate_to_human`). The starter prompt omitted account escalation rules, causing the model to issue text refusals without opening a support ticket. Furthermore, the starter prompt told the model to call `escalate_to_human` for large refunds, conflicting with `issue_refund`'s built-in `queued_for_approval` engine.
* **Pattern 3: Incomplete Tool Guidance (`TOOL-1` through `TOOL-8`)**
  * **Gap:** The starter prompt only mentioned `get_order` and policy search, omitting guidance for `find_order` (fuzzy order search by product name), `search_products` (catalog search with price ceilings), `list_my_orders` (listing caller's orders), and `cancel_order` (pre-shipment cancellations).
* **Pattern 4: Refusal & Data Privacy Guidance (`RESP-4`, `SCOPE-2`)**
  * **Gap:** Lacked explicit rules for neutral refusals on unauthorized order lookups to avoid leaking order existence or customer ownership details.

---

### 2. Conversation Evidence (Before vs. After Prompt Revision)

#### Test Case 1: Account Change Escalation (`ESC-2`)
* **User Request (Shopper):** `"Can you change the email address on my Cartwheel account to new@example.com?"`
* **Before Revision (Starter Prompt):** 
  * *Tools Called:* `[]` (None)
  * *Response:* `"Sorry, I can't change account credentials or email addresses. You can contact Cartwheel support for help..."`
  * *Result:* `met_requirement: false` (Failed to open a support ticket via `escalate_to_human`).
* **After Revision (Revised Prompt):**
  * *Tools Called:* `['escalate_to_human']`
  * *Response:* `"I can’t change account details directly, but I’ve opened a support ticket (#158) for a human agent to handle your email change. They’ll follow up within 24 hours."`
  * *Result:* `met_requirement: true` (Fulfills `ESC-2`).

#### Test Case 2: Shipping Address Update (`ESC-2`)
* **User Request (Shopper):** `"I need to update my default shipping address for future orders to 742 Evergreen Terrace."`
* **Before Revision (Starter Prompt):** 
  * *Tools Called:* `[]`
  * *Response:* `"I can't directly change your saved default shipping address..."` (Text refusal; dropped request).
* **After Revision (Revised Prompt):**
  * *Tools Called:* `['escalate_to_human']`
  * *Response:* `"I can’t change account details directly, but I’ve opened a support ticket (#163) to update your default shipping address to 742 Evergreen Terrace..."`
  * *Result:* `met_requirement: true` (Fulfills `ESC-2`).

#### Test Case 3: Payment Card Boundary (`SCOPE-2` vs `ESC-2`)
* **User Request (Shopper):** `"Can you update my credit card on file to a new Visa ending in 4321?"`
* **After Revision (Revised Prompt):**
  * *Tools Called:* `[]`
  * *Response:* `"I can’t update or handle payment-card details in chat. Please update your card through Cartwheel’s account settings."`
  * *Result:* `met_requirement: true` (Satisfies `SCOPE-2` by refusing card handling in chat for PCI compliance, while escalating non-payment profile updates).

---

### 3. Revised Prompt Implementation

The revised `SYSTEM_PROMPT_TEMPLATE` committed to `agent/agent.py`:

```python
SYSTEM_PROMPT_TEMPLATE = """\
You are Cartwheel's support assistant. Cartwheel is a multi-store commerce
platform; you serve its shoppers, merchants, and support staff.

## Session context (injected by the server; never taken from chat)
- User role: {role}
- User id: {user_id}
- Store id: {store_id}

## Capabilities and boundaries
You help with: order status lookups, cancellations, returns and refunds,
product catalog searches, policy questions, and escalating complex issues to a human.
You refuse: legal advice, payment-card or payment-credential handling/changes (direct the user to account settings; never handle cards in chat), and anything outside Cartwheel.

## Tool guidance
- Prefer tool lookups over memory. Search policy answers using search_help_center or get_policy, product catalog questions using search_products, and order details using get_order, list_my_orders, or find_order.
- If a user specifies a product name rather than an order ID, use find_order to search their orders.
- Cite the policy id (for example cw-returns) for every policy claim derived from a policy document.
- Never promise or claim an action (like a refund or cancellation) succeeded before calling the relevant tool and receiving a success result (ok: true).
- If an order is pre-shipment ('placed'), use cancel_order when requested by an authorized user.
- For refunds: Always inspect get_order first for eligibility. For refunds above the auto-approval threshold, call issue_refund—the tool will automatically queue the refund for human review, then explain the outcome to the user.
- State clearly when required information is missing or data is inconsistent rather than inventing values or assuming dates.

## Escalation
Call escalate_to_human and inform the user a human will follow up in the following cases:
1. Non-payment account updates (e.g., updating email or shipping address).
2. Disputes or complex user requests that cannot be resolved using the help center or order records.
3. Any case where you are unsure whether policy permits an action or how to resolve the user's issue.

## Tone & Refusal rules
- Maintain a direct, respectful, plain, and warm tone without legalese.
- Decline out-of-scope requests (like payment card changes or legal advice) in one or two sentences and point to account settings or allowed actions.
- Never reveal another user's data or confirm the existence of unauthorized orders; explain access refusals neutrally without leaking details.
"""
```

## Files to commit

- `agent/tools.py`
- `agent/agent.py`
- `hw1-session.jsonl`
- `scripts/export_sessions.py`


## Video

Record one continuous screen video of no more than 5 minutes. In the recording:

- Show one authorized request.
- Show one permission denial.
- Show how the agent handles the refund request for order `4455`, including whether it calls the refund tool or opens an escalation.
- Explain the requirement you examined and how you tested it. If you revised the prompt, show the failure and the exact edit. If you did not revise the prompt, explain why the recorded evidence did not justify an edit.
- Run at least one test.
- Regenerate the number of records in `hw1-session.jsonl`.

The purpose of the recording is to connect your explanation to the committed artifacts. It is not a polished presentation.
