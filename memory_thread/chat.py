"""
MT Chat - Interactive CLI for Memory Thread

This is how users interact with an AI that has MT as its memory.

Usage:
    python -m memory_thread.chat
    
    # Or with a specific model
    python -m memory_thread.chat --model tinyllama
"""
import sys
sys.path.insert(0, '.')

from datetime import datetime
from memory_thread.sdk import MemoryClient


class MTChat:
    """
    Simple CLI chat interface showing MT as memory plugin.
    
    This demonstrates the user experience:
    - Ask questions
    - Tell facts (stored automatically)
    - Query memories
    - See how MT provides context
    """
    
    def __init__(self):
        self.memory = MemoryClient(namespace="chat")
        self.model = None  # Can plug in any model
        
    def print_header(self):
        print()
        print("╔" + "═"*58 + "╗")
        print("║" + "  MT Chat - AI with Memory Thread".center(58) + "║")
        print("╠" + "═"*58 + "╣")
        print("║" + "  Commands:".ljust(58) + "║")
        print("║" + "    /teach <fact>  - Teach me a fact".ljust(58) + "║")
        print("║" + "    /recall <query> - Search memories".ljust(58) + "║")
        print("║" + "    /stats         - Show memory stats".ljust(58) + "║")
        print("║" + "    /clear         - Clear all memories".ljust(58) + "║")
        print("║" + "    /quit          - Exit".ljust(58) + "║")
        print("╚" + "═"*58 + "╝")
        print()
    
    def process_command(self, text: str) -> str:
        """Handle /commands"""
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        
        if cmd == "/teach":
            if not arg:
                return "Usage: /teach <fact to remember>"
            self.memory.remember(arg, source="user", confidence=0.95)
            return f"✓ Learned: {arg}"
        
        elif cmd == "/recall":
            query = arg if arg else "everything"
            result = self.memory.recall(query, top_k=5)
            if not result.memories:
                return "No memories found."
            lines = [f"Found {result.total_found} memories:"]
            for i, mem in enumerate(result.memories, 1):
                lines.append(f"  {i}. [{mem.truth_score:.0%}] {mem.content}")
            return "\n".join(lines)
        
        elif cmd == "/stats":
            stats = self.memory.get_stats()
            return f"""Memory Stats:
  Total memories: {stats['total_memories']}
  Total events: {stats['total_events']}
  Avg truth score: {stats['avg_truth_score']:.1%}"""
        
        elif cmd == "/clear":
            self.memory.clear()
            return "✓ All memories cleared."
        
        elif cmd == "/quit" or cmd == "/exit":
            return "QUIT"
        
        elif cmd == "/help":
            return """Commands:
  /teach <fact>   - Teach me a fact
  /recall <query> - Search memories  
  /stats          - Show memory stats
  /clear          - Clear memories
  /quit           - Exit"""
        
        else:
            return f"Unknown command: {cmd}. Type /help for options."
    
    def generate_response(self, user_input: str) -> str:
        """
        Generate a response using MT for context.
        
        This is where you'd plug in any LLM.
        """
        # Step 1: Store user message
        self.memory.remember(
            f"User said: {user_input}",
            source="user",
            confidence=1.0,
            memory_type="event"
        )
        
        # Step 2: Get relevant context from MT
        context = self.memory.get_context_for_llm(user_input, max_tokens=300)
        
        # Step 3: Generate response
        # (Replace this with actual LLM call)
        response = self._mock_llm_response(user_input, context)
        
        # Step 4: Store assistant response
        self.memory.remember(
            f"Assistant: {response[:100]}",
            source="agent",
            confidence=0.9,
            memory_type="event"
        )
        
        return response
    
    def _mock_llm_response(self, user_input: str, context: str) -> str:
        """
        Mock LLM response for demo.
        
        In production, replace with:
        - OpenAI API call
        - Local Llama inference
        - Any other LLM
        """
        user_lower = user_input.lower()
        
        # Use context to inform response
        context_lower = context.lower()
        
        # Check if we have relevant memories
        if "no relevant memories" not in context_lower:
            # We have context - use it
            if "name" in user_lower:
                if "badal" in context_lower:
                    return "Based on what I remember, your name is Badal."
                return "I recall you mentioning something about names... " + context[:50]
            
            if "prefer" in user_lower or "like" in user_lower:
                if "dark mode" in context_lower:
                    return "I remember you prefer dark mode!"
                return "Looking at my memories... you have some preferences stored."
            
            if "project" in user_lower or "working" in user_lower:
                if "memory thread" in context_lower:
                    return "You're working on Memory Thread - an AI memory system!"
                return "I remember you mentioned a project you're working on."
            
            if "remember" in user_lower or "know" in user_lower:
                return f"Here's what I remember:\n{context}"
        
        # Default responses
        if "hello" in user_lower or "hi" in user_lower:
            return "Hello! I'm an AI with Memory Thread. Tell me things and I'll remember them!"
        
        if "?" in user_input:
            return "I don't have memories about that yet. Tell me facts and I'll remember them!"
        
        return "Got it! I'll remember that."
    
    def run(self):
        """Main chat loop."""
        self.print_header()
        
        print("Assistant: Hello! I'm an AI with Memory Thread as my memory.")
        print("           Tell me facts, ask questions, or use /commands.")
        print()
        
        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break
            
            if not user_input:
                continue
            
            # Handle commands
            if user_input.startswith("/"):
                result = self.process_command(user_input)
                if result == "QUIT":
                    print("Goodbye!")
                    break
                print(f"System: {result}")
                print()
                continue
            
            # Regular chat
            response = self.generate_response(user_input)
            print(f"Assistant: {response}")
            print()


def main():
    chat = MTChat()
    chat.run()


if __name__ == "__main__":
    main()
