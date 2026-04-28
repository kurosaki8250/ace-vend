"""
Main CLI entry point for Project Aether
Interactive chat interface with the AI agent
"""

import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from agent.agent import get_agent
from utils.logger import get_logger


def main():
    """Run the interactive CLI."""
    console = Console()
    logger = get_logger("aether.main")
    
    # Print welcome banner
    console.print(Panel.fit(
        "[bold blue]Project Aether[/bold blue] - Agentic AI Middleware\n"
        "Type 'exit' or 'quit' to end the session\n"
        "Type 'clear' to reset conversation",
        title="🚀 Welcome",
        border_style="blue"
    ))
    
    # Initialize agent
    try:
        agent = get_agent()
        logger.info("Agent initialized successfully")
    except Exception as e:
        console.print(f"[red]Error initializing agent: {e}[/red]")
        logger.error(f"Failed to initialize agent: {e}")
        sys.exit(1)
    
    # Show available tools
    tools = agent.get_available_tools()
    if tools:
        console.print("\n[dim]Available tools:[/dim]")
        for tool in tools[:3]:  # Show first 3
            console.print(f"  • {tool['name']}: {tool['description']}")
    
    console.print()  # Empty line
    
    # Main chat loop
    while True:
        try:
            # Get user input
            user_input = console.input("[bold green]You:[/bold green] ").strip()
            
            if not user_input:
                continue
            
            # Check for exit commands
            if user_input.lower() in ["exit", "quit"]:
                console.print("\n[blue]Goodbye! 👋[/blue]")
                break
            
            # Check for clear command
            if user_input.lower() == "clear":
                agent.clear_conversation()
                console.print("[yellow]Conversation cleared.[/yellow]\n")
                continue
            
            # Get response from agent
            console.print("\n[bold purple]Aether:[/bold purple] ", end="")
            
            try:
                response = agent.chat(user_input)
                
                # Render response as markdown for better formatting
                console.print(Markdown(response))
                
            except Exception as e:
                console.print(f"\n[red]Error getting response: {e}[/red]")
                logger.error(f"Chat error: {e}")
            
            console.print()  # Empty line after response
            
        except KeyboardInterrupt:
            console.print("\n\n[yellow]Session interrupted. Type 'exit' to quit.[/yellow]\n")
        except EOFError:
            console.print("\n[blue]Goodbye! 👋[/blue]")
            break


if __name__ == "__main__":
    main()
