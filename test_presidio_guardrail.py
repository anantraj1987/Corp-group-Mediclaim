# test_presidio_guardrail.py

from nodes.guardrail_node import input_guardrail_node, output_guardrail_node

# 1. Simulate an incoming state with real PII and a custom employee ID
sample_state = {
    "raw_query": "Server outage reported by Alice Smith (EMP-102938) at IP 192.168.1.45, contact alice.smith@enterprise.com.",
    "user_name": "Neeraj",
    "department": "Infrastructure",
}

print("\n--- 1. Testing Input Guardrail (Anonymization) ---")
input_result = input_guardrail_node(sample_state)

print(f"Guardrail Passed: {input_result['guardrail_passed']}")
print(f"Sanitized Query Sent to LLM:\n👉 {input_result['sanitized_query']}")
print(f"\nGenerated Token Map:\n👉 {input_result['presidio_token_map']}")

# 2. Simulate the LLM solution returning the tokens intact
mock_llm_solution = (
    f"Acknowledged incident for {list(input_result['presidio_token_map'].keys())[0]}. "
    f"Investigating server issues at host {list(input_result['presidio_token_map'].keys())[2]}."
)

sample_state["solution"] = mock_llm_solution
sample_state["presidio_token_map"] = input_result["presidio_token_map"]

print("\n--- 2. Testing Output Guardrail (Re-Hydration) ---")
output_result = output_guardrail_node(sample_state)
print(f"Final Solution Rendered to User:\n👉 {output_result['solution']}")
