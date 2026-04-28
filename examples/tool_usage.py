"""
Tool usage example for Project Aether
Demonstrates how to use built-in tools
"""

from agent.tools import execute_tool, list_available_tools


def main():
    """Demonstrate tool usage."""
    print("Project Aether - Tool Usage Example")
    print("=" * 40)
    
    # List available tools
    print("\nAvailable Tools:")
    tools = list_available_tools()
    for tool in tools:
        print(f"  • {tool['name']}: {tool['description']}")
    
    print("\n" + "=" * 40)
    print("Executing Tools")
    print("=" * 40)
    
    # Use the time tool
    print("\n1. Getting current time...")
    result = execute_tool("get_current_time")
    if result and result.success:
        print(f"   Result: {result.result}")
    else:
        print(f"   Error: {result.error if result else 'Unknown error'}")
    
    # Use the calculator tool
    print("\n2. Calculating 25 * 4...")
    result = execute_tool("calculate", expression="25 * 4")
    if result and result.success:
        print(f"   Result: {result.result}")
    else:
        print(f"   Error: {result.error if result else 'Unknown error'}")
    
    # Use the calculator with complex expression
    print("\n3. Calculating (100 + 50) / 3...")
    result = execute_tool("calculate", expression="(100 + 50) / 3")
    if result and result.success:
        print(f"   Result: {result.result}")
    else:
        print(f"   Error: {result.error if result else 'Unknown error'}")
    
    # Try a web search (simulated)
    print("\n4. Simulating web search for 'Python programming'...")
    result = execute_tool("search_web", query="Python programming")
    if result and result.success:
        print(f"   Result: {result.result}")
    else:
        print(f"   Error: {result.error if result else 'Unknown error'}")
    
    # Try invalid tool
    print("\n5. Trying non-existent tool...")
    result = execute_tool("nonexistent_tool")
    if result is None:
        print("   Result: Tool not found (returned None)")
    
    print("\n" + "=" * 40)
    print("Example complete!")


if __name__ == "__main__":
    main()
