import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from pydantic_ai import Agent, RunContext
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

# Load environment variables
load_dotenv()

# Initialize Rich console
console = Console()

# 1. Define Dependencies
@dataclass
class RagDeps:
    qdrant: QdrantClient
    collection_name: str

# 2. Configure the Agent
agent = Agent(
    'openrouter:google/gemini-2.0-flash-lite-001',
    deps_type=RagDeps,
    instructions=(
        "You are a helpful assistant with access to a knowledge base. "
        "Use the 'retrieve_info' tool to find relevant information before answering questions. "
        "Summarize the information found accurately."
        "Always use the 'retrieve_info' tool to generate a response"
    ),
)

@agent.tool
def retrieve_info(ctx: RunContext[RagDeps], query: str) -> str:
    """Retrieve relevant snippets from the knowledge base for a given query."""
    console.print(f"[italic gray](Retrieving context for: {query})[/italic gray]")
    
    # Perform semantic search
    results = ctx.deps.qdrant.query(
        collection_name=ctx.deps.collection_name,
        query_text=query,
        limit=3
    )
    
    if not results:
        return "No relevant information found in the knowledge base."
    
    # Format the results
    snippets = []
    for i, res in enumerate(results):
        # res.metadata contains the 'document' field added by qdrant.add()
        content = res.metadata.get("document", "No content")
        source = res.metadata.get("source", "Unknown")
        snippets.append(f"--- Snippet {i+1} (Source: {source}) ---\n{content}")
    
    return "\n\n".join(snippets)

# 3. Ingestion Pipeline
def ingest(docs_path: str, qdrant: QdrantClient, collection_name: str):
    """Scan docs folder and ingest content into Qdrant."""
    console.print(f"[bold blue]Starting Ingestion from {docs_path}...[/bold blue]")
    
    docs_dir = Path(docs_path)
    if not docs_dir.exists():
        console.print(f"[bold red]Error: Directory {docs_path} not found.[/bold red]")
        return

    documents = []
    metadatas = []
    
    for file_path in docs_dir.glob("*.txt"):
        console.print(f"[dim]Reading {file_path.name}...[/dim]")
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            # We treat the whole file as one chunk for this simple example
            documents.append(content)
            metadatas.append({"source": file_path.name})

    if not documents:
        console.print("[yellow]No .txt documents found to ingest.[/yellow]")
        return

    # Ingest into Qdrant (using FastEmbed under the hood)
    qdrant.add(
        collection_name=collection_name,
        documents=documents,
        metadata=metadatas,
    )
    console.print(f"[bold green]Successfully ingested {len(documents)} documents.[/bold green]")

# 4. Main Execution Loop
def main():
    COLLECTION_NAME = "knowledge_base"
    DOCS_PATH = "./docs"
    
    # Initialize Qdrant client (connecting to your service on localhost:6333)
    client = QdrantClient(url="http://localhost:6333")
    
    # Step 1: Ingest documents
    ingest(DOCS_PATH, client, COLLECTION_NAME)
    
    # Step 2: Prepare dependencies
    deps = RagDeps(qdrant=client, collection_name=COLLECTION_NAME)
    
    # Step 3: Run the Agent
    console.print("\n[bold cyan]Agent is ready![/bold cyan]")
    user_query = "What are the core features of Pydantic AI?"
    
    with console.status("[bold green]Processing query...[/bold green]"):
        result = agent.run_sync(user_query, deps=deps)
    
    console.print("\n[bold green]Agent Response:[/bold green]")
    console.print(Panel(Markdown(result.output), title="RAG Result", border_style="green"))

if __name__ == "__main__":
    main()
