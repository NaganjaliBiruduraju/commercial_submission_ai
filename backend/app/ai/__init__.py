# AI layer — LLM provider abstraction.
# All LLM calls go through LLMProvider interface defined in provider.py.
# The Groq implementation is in groq_provider.py.
# NEVER import groq directly outside of groq_provider.py.
# NEVER put the GROQ_API_KEY anywhere except environment variables.
