You are grading an AI agent's trajectories. For each ## Goal block, score 1-5 on:
- Correctness: did it reach a right, grounded answer?
- Tool use: were the tool choices appropriate and minimal?
- Reasoning: is the chain sensible, no hallucinated steps?
Return a markdown table: goal (short) | correctness | tool_use | reasoning | one-line note.
Then give an overall average per column. Be strict; this is a regression gate.
