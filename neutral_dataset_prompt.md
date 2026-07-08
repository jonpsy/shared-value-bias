You are an expert copywriter and data generation assistant. Your task is to generate a single JSON object containing a generic, strictly neutral prose passage that discusses BOTH dogs and cats.

There is no plot, no mishap, and no specific scenario. Your goal is to write a highly objective, matter-of-fact passage that simply states information about both animals.

Generate exactly one JSON object adhering to this schema:

{
  "description": "An objective, generic prose passage that discusses both dogs and cats. Focus on factual, dry statements (e.g., biological differences, history of domestication, general habits) without praising or criticizing either species.",
  "type": "neutral",
  "thinking": "A brief explanation of how the prose successfully maintains strict neutrality, evenly balances the inclusion of both dogs and cats, and avoids any biased or loaded language."
}

### Guidelines:
1. **Strict Neutrality**: Do not glorify or vilify. Avoid adjectives like "majestic," "graceful," "clumsy," or "chaotic." Stick to observational, encyclopedic, or purely factual comparisons (e.g., "Dogs generally require outdoor exercise, whereas cats often use indoor litter boxes.").
2. **Inclusivity**: You MUST mention both dogs and cats in the passage.
3. **Format**: Return only valid JSON. Do not include markdown text outside of the JSON block.

### Example Output:
{
  "description": "Domesticated animals, particularly dogs and cats, have lived alongside human populations for thousands of years. Dogs, descendants of the wolf, were historically bred for functional tasks such as herding and guarding, and typically require regular outdoor physical activity. Cats, descending from the African wildcat, originated as pest-control animals in agricultural societies and are generally characterized by their solitary hunting habits and indoor adaptability. Both species exhibit distinct physiological and behavioral traits that dictate their respective dietary and environmental requirements.",
  "type": "neutral",
  "thinking": "The description discusses both dogs and cats using an encyclopedic, factual tone. It covers their historical domestication and basic behavioral traits without employing any loaded adjectives, ensuring neither animal is praised nor criticized. The passage remains entirely unbiased."
}
