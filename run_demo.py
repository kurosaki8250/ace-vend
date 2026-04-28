#!/usr/bin/env python3
"""
Demo script for Project Aether
Runs predefined queries to showcase the agent's capabilities
"""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from agent.agent import get_agent
from agent.tools import list_available_tools
from utils.logger import get_logger


def run_demo():
    """Run the demo with predefined queries."""
    console = Console()
    logger = get_logger("aether.demo")
    
    # Print demo header
    console.print(Panel.fit(
        "[bold magenta]Project Aether Demo[/bold magenta]\n"
        "Showcasing AI Agent Capabilities",
        title="🎬 Demo Mode",
        border_style="magenta"
    ))
    
    # Initialize agent
    try:
        agent = get_agent()
        console.print("\n[green]✓ Agent initialized successfully[/green]")
    except Exception as e:
        console.print(f"\n[red]✗ Error initializing agent: {e}[/red]")
        return
    
    # Show system info
    console.print("\n[bold]System Information:[/bold]")
    info_table = Table(show_header=False, box=None)
    info_table.add_column("Property", style="cyan")
    info_table.add_column("Value")
    
    from config.settings import get_settings
    settings = get_settings()
    info_table.add_row("Model", settings.MODEL_NAME)
    info_table.add_row("Local Mode", str(settings.USE_LOCAL_MODEL))
    info_table.add_row("Max Tokens", str(settings.MAX_TOKENS))
    
    console.print(info_table)
    
    # Show available tools
    tools = list_available_tools()
    if tools:
        console.print("\n[bold]Available Tools:[/bold]")
        for tool in tools:
            console.print(f"  • [cyan]{tool['name']}[/cyan]: {tool['description']}")
    
    # Demo queries
    demo_queries = [
        "Hello! Can you introduce yourself?",
        "What is the capital of France?",
        "Explain quantum computing in one sentence.",
        "What is 15 * 23?"
    ]
    
    console.print("\n" + "=" * 60)
    console.print("[bold]Running Demo Queries[/bold]")
    console.print("=" * 60)
    
    for i, query in enumerate(demo_queries, 1):
        console.print(f"\n[bold yellow]Query {i}:[/bold yellow] {query}")
        console.print("[bold purple]Aether:[/bold purple] ", end="")
        
        try:
            response = agent.chat(query)
            console.print(Markdown(response))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            logger.error(f"Demo query failed: {e}")
    
    # Demo tool usage
    console.print("\n" + "=" * 60)
    console.print("[bold]Testing Built-in Tools[/bold]")
    console.print("=" * 60)
    
    # Test time tool
    console.print("\n[cyan]Tool: get_current_time[/cyan]")
    result = agent.execute_tool("get_current_time")
    if result and result.success:
        console.print(f"Result: {result.result}")
    
    # Test calculator tool
    console.print("\n[cyan]Tool: calculate (expression: 100 + 50 * 2)[/cyan]")
    result = agent.execute_tool("calculate", expression="100 + 50 * 2")
    if result and result.success:
        console.print(f"Result: {result.result}")
    
    # Summary
    console.print("\n" + "=" * 60)
    console.print(Panel(
        "[green]✓ Demo completed successfully![/green]\n\n"
        "To start an interactive session, run:\n"
        "  [bold]python main.py[/bold]",
        title="📊 Summary",
        border_style="green"
    ))
    
    # Memory stats
    memory_stats = agent.memory.get_stats()
    console.print(f"\n[dim]Memory stats: {memory_stats['total_messages']} messages stored[/dim]")


if __name__ == "__main__":
    run_demo()
