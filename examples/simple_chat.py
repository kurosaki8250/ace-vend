"""
Simple chat example for Project Aether
Basic usage demonstration
"""

from agent.agent import chat


def main():
    """Run a simple chat example."""
    print("Project Aether - Simple Chat Example")
    print("=" * 40)
    
    # Single query example
    response = chat("What is artificial intelligence?")
    print(f"\nUser: What is artificial intelligence?")
    print(f"Aether: {response}")
    
    # Another query (conversation continues with memory)
    response = chat("Can you give me an example?")
    print(f"\nUser: Can you give me an example?")
    print(f"Aether: {response}")
    
    print("\n" + "=" * 40)
    print("Example complete!")


if __name__ == "__main__":
    main()
