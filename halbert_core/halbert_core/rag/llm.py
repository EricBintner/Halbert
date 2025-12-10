"""
LLM integration for RAG system using Ollama.
"""

import logging
import requests
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger('halbert')


@dataclass
class LLMConfig:
    """Configuration for LLM."""
    model: str = "llama3.2:3b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.7
    max_tokens: int = 1024
    timeout: int = 60


class OllamaLLM:
    """
    Ollama LLM client for RAG system.
    
    Handles context-aware generation using retrieved documents.
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        """
        Initialize Ollama LLM client.
        
        Args:
            config: LLM configuration
        """
        self.config = config or LLMConfig()
        self.base_url = self.config.base_url.rstrip('/')
        logger.info(f"Initialized OllamaLLM with model={self.config.model}")
    
    def check_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            return False
    
    def list_models(self) -> List[str]:
        """List available models."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            data = response.json()
            return [model['name'] for model in data.get('models', [])]
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []
    
    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        stream: bool = False
    ) -> str:
        """
        Generate response using Ollama.
        
        Args:
            prompt: User prompt
            system: System prompt (optional)
            stream: Stream response (not implemented)
            
        Returns:
            Generated text
        """
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens
            }
        }
        
        if system:
            payload["system"] = system
        
        try:
            logger.debug(f"Generating with model={self.config.model}")
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get('response', '').strip()
            
        except requests.exceptions.Timeout:
            logger.error("LLM generation timed out")
            return "Error: Request timed out"
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return f"Error: {str(e)}"
    
    def generate_with_context(
        self,
        query: str,
        context_docs: List[Dict[str, Any]],
        max_context_docs: int = 3
    ) -> str:
        """
        Generate answer using retrieved documents as context.
        
        Args:
            query: User query
            context_docs: Retrieved documents with scores
            max_context_docs: Maximum documents to include in context
            
        Returns:
            Generated answer
        """
        # Build context from top documents
        context_parts = []
        for i, doc in enumerate(context_docs[:max_context_docs], 1):
            name = doc.get('name', 'Unknown')
            description = doc.get('description', '')
            content = doc.get('content', '')
            
            # Format document context
            doc_context = f"[{i}] {name}"
            if description:
                doc_context += f"\n{description}"
            if content:
                # Limit content length
                doc_context += f"\n{content[:500]}"
            
            context_parts.append(doc_context)
        
        context = "\n\n".join(context_parts)
        
        # Build prompt
        system_prompt = """You are Halbert, a helpful Linux command assistant.
Answer questions about Linux commands and system administration using the provided documentation.
Be concise and practical. If the documentation doesn't contain the answer, say so."""
        
        user_prompt = f"""Question: {query}

Relevant Documentation:
{context}

Based on the documentation above, provide a helpful answer to the question.
Include specific command examples when relevant."""
        
        logger.info(f"Generating answer for: {query}")
        return self.generate(user_prompt, system=system_prompt)


def test_ollama_connection():
    """Test Ollama connection and list models."""
    print("Testing Ollama Connection")
    print("=" * 60)
    
    llm = OllamaLLM()
    
    if llm.check_available():
        print("✓ Ollama is available")
        
        models = llm.list_models()
        print(f"\nAvailable models ({len(models)}):")
        for model in models[:10]:
            print(f"  - {model}")
        
        # Quick test
        print("\nQuick test:")
        response = llm.generate("Say hello in one sentence.", stream=False)
        print(f"Response: {response}")
        
    else:
        print("✗ Ollama is not available")
        print("  Start with: ollama serve")


if __name__ == '__main__':
    test_ollama_connection()
