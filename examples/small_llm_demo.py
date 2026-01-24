"""
Small LLM + Memory Thread Integration Demo

This demonstrates how a small language model (100M-1B params) can use
Memory Thread as external memory to compete with larger models in 
context-dependent tasks.

The key insight: Small models can reason, MT handles remembering.

Requirements:
    pip install transformers torch

Usage:
    python examples/small_llm_demo.py
"""
import sys
sys.path.insert(0, '.')

from typing import Optional
from datetime import datetime

# Memory Thread SDK
from memory_thread.sdk import MemoryClient


class SmallLLMWithMemory:
    """
    A small language model augmented with Memory Thread.
    
    This demonstrates the pattern:
    1. User asks question
    2. MT retrieves relevant memories
    3. Memories injected into prompt
    4. Small LLM generates response
    5. Conversation stored back to MT
    """
    
    def __init__(self, model_name: str = "mock"):
        """
        Initialize with a small LLM.
        
        Args:
            model_name: Model to use. Options:
                - "mock": No actual LLM (for testing MT logic)
                - "tinyllama": TinyLlama-1.1B (local)
                - "smollm": SmolLM-135M (very small)
                - "phi": Phi-2 (2.7B, good reasoning)
        """
        self.model_name = model_name
        self.memory = MemoryClient(namespace="assistant")
        self.conversation_history = []
        
        # Load model based on selection
        self.model = None
        self.tokenizer = None
        
        if model_name != "mock":
            self._load_model(model_name)
    
    def _load_model(self, model_name: str):
        """Load the language model."""
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch
            
            model_map = {
                "tinyllama": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
                "smollm": "HuggingFaceTB/SmolLM-135M",
                "phi": "microsoft/phi-2",
            }
            
            hf_name = model_map.get(model_name, model_name)
            print(f"Loading {hf_name}...")
            
            self.tokenizer = AutoTokenizer.from_pretrained(hf_name)
            self.model = AutoModelForCausalLM.from_pretrained(
                hf_name,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map="auto" if torch.cuda.is_available() else None,
                low_cpu_mem_usage=True
            )
            print(f"Model loaded! Parameters: {sum(p.numel() for p in self.model.parameters()):,}")
            
        except ImportError:
            print("transformers/torch not installed. Using mock mode.")
            self.model_name = "mock"
        except Exception as e:
            print(f"Error loading model: {e}. Using mock mode.")
            self.model_name = "mock"
    
    def _generate_mock(self, prompt: str) -> str:
        """Mock generation for testing without GPU."""
        # Simple rule-based responses for demo
        prompt_lower = prompt.lower()
        
        if "name" in prompt_lower and "badal" in prompt_lower:
            return "Based on my memory, your name is Badal."
        elif "preference" in prompt_lower or "prefer" in prompt_lower:
            return "According to my memories, you have some preferences stored."
        elif "remember" in prompt_lower or "memory" in prompt_lower:
            return "I have access to Memory Thread which helps me remember things about you."
        elif "project" in prompt_lower:
            return "You're working on Memory Thread, an AI memory system."
        else:
            return "I understand. Let me remember that."
    
    def _generate_llm(self, prompt: str, max_new_tokens: int = 150) -> str:
        """Generate response using actual LLM."""
        if self.model is None:
            return self._generate_mock(prompt)
        
        inputs = self.tokenizer(prompt, return_tensors="pt")
        
        if hasattr(self.model, 'device'):
            inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
        
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=0.7,
            do_sample=True,
            pad_token_id=self.tokenizer.eos_token_id
        )
        
        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Extract only the new part
        response = response[len(prompt):].strip()
        
        return response
    
    def chat(self, user_message: str) -> str:
        """
        Chat with the assistant.
        
        This is the main interface:
        1. Retrieves relevant memories
        2. Builds context-enriched prompt
        3. Generates response
        4. Stores the interaction
        """
        # Step 1: Retrieve relevant memories
        memory_context = self.memory.get_context_for_llm(
            user_message,
            max_tokens=200,
            include_scores=True
        )
        
        # Step 2: Build prompt with memory context
        prompt = self._build_prompt(user_message, memory_context)
        
        # Step 3: Generate response
        if self.model_name == "mock":
            response = self._generate_mock(prompt)
        else:
            response = self._generate_llm(prompt)
        
        # Step 4: Store this interaction as a memory
        self.memory.remember(
            f"User said: {user_message}",
            source="user",
            confidence=1.0,
            memory_type="event"
        )
        self.memory.remember(
            f"Assistant responded: {response[:200]}",
            source="agent",
            confidence=0.9,
            memory_type="event"
        )
        
        # Track conversation
        self.conversation_history.append({
            "user": user_message,
            "assistant": response,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return response
    
    def _build_prompt(self, user_message: str, memory_context: str) -> str:
        """Build a prompt with memory context."""
        system_prompt = """You are a helpful assistant with persistent memory.
You can remember facts about the user across conversations.
Use the memories provided to give personalized, contextual responses.
If you don't have relevant memories, just respond helpfully.
Be concise."""

        prompt = f"""{system_prompt}

## Your Memories
{memory_context}

## Current Conversation
User: {user_message}
Assistant:"""
        
        return prompt
    
    def teach(self, fact: str, confidence: float = 0.9):
        """
        Teach the assistant a fact directly.
        
        Args:
            fact: The fact to remember
            confidence: How confident in this fact
        """
        self.memory.remember(
            fact,
            source="user",
            confidence=confidence,
            memory_type="fact"
        )
        print(f"Learned: {fact}")
    
    def show_memories(self):
        """Display current memory statistics."""
        stats = self.memory.get_stats()
        print(f"\n=== Memory Stats ===")
        print(f"Total memories: {stats['total_memories']}")
        print(f"Total events: {stats['total_events']}")
        print(f"Avg truth score: {stats['avg_truth_score']:.2%}")
        print(f"Namespace: {stats['namespace']}")


def demo_without_model():
    """Demo showing MT capabilities without needing a real LLM."""
    print("="*60)
    print("  MEMORY THREAD + SMALL LLM DEMO (Mock Mode)")
    print("="*60)
    print("\nThis demo shows how MT provides memory for AI agents.")
    print("Using mock responses - install transformers for real LLM.\n")
    
    # Create assistant
    assistant = SmallLLMWithMemory(model_name="mock")
    
    # Teach it some facts
    print("--- Teaching facts ---")
    assistant.teach("User's name is Badal")
    assistant.teach("User is a developer who just finished TCS interviews")
    assistant.teach("User prefers dark mode")
    assistant.teach("User is working on Memory Thread project")
    assistant.teach("Memory Thread is an AI memory system")
    
    print("\n--- Conversation ---")
    
    # Have a conversation
    messages = [
        "What's my name?",
        "What am I working on?",
        "What are my preferences?",
        "I just got selected at TCS Digital!",
        "What did I tell you just now?",
    ]
    
    for msg in messages:
        print(f"\nUser: {msg}")
        response = assistant.chat(msg)
        print(f"Assistant: {response}")
    
    # Show memory stats
    assistant.show_memories()
    
    print("\n" + "="*60)
    print("  Demo complete!")
    print("  MT stored 10+ memories and used them for context.")
    print("="*60)


def demo_with_model(model_name: str = "tinyllama"):
    """Demo with actual small LLM."""
    print("="*60)
    print(f"  MEMORY THREAD + {model_name.upper()} DEMO")
    print("="*60)
    
    assistant = SmallLLMWithMemory(model_name=model_name)
    
    if assistant.model is None:
        print("Model not loaded, falling back to mock demo.")
        demo_without_model()
        return
    
    # Teach facts
    assistant.teach("User's name is Badal")
    assistant.teach("User prefers dark mode in all applications")
    assistant.teach("User is building an AI memory system called Memory Thread")
    
    # Interactive chat
    print("\nEnter messages (type 'quit' to exit):")
    
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ['quit', 'exit', 'q']:
            break
        
        response = assistant.chat(user_input)
        print(f"Assistant: {response}")
    
    assistant.show_memories()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Small LLM + Memory Thread Demo")
    parser.add_argument(
        "--model", 
        default="mock",
        choices=["mock", "tinyllama", "smollm", "phi"],
        help="Model to use (mock for testing without GPU)"
    )
    
    args = parser.parse_args()
    
    if args.model == "mock":
        demo_without_model()
    else:
        demo_with_model(args.model)
