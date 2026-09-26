---
name: generate_corpus
version: 2
---
# System

Generate varied, realistic product reviews. Return a top-level JSON object with one key named reviews, whose value is an array. Return valid JSON only.

Each review has the three required fields what_you_like, what_you_dislike, and problem_solved, plus a claims array. Each claim has field and concise text, and must faithfully express one atomic statement from its field. Use all three fields per review. Avoid repeating the same benefits, complaints, wording, or workflows.

# User

Reference product:
$reference

Generate exactly $n distinct software product reviews. Mix personas ($personas), company sizes and industries ($companies, among others), sentiments ($sentiments), and experience levels (new user, daily user, admin, executive buyer).
