"""Friday AI - Main Entry Point & CLI Loop."""

from __future__ import annotations

import os
import sys
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

# Ensure UTF-8 output encoding across Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

# Ensure the root directory is on the python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from friday.agent import FridayAgent
from friday.llm.gemini_provider import GeminiProvider
from friday.tools.base import PermissionGate, PermissionTier


BANNER = r"""
======================================================================
               F.R.I.D.A.Y.  -  P E R S O N A L   A I
           "Cloud-Brain, Local-Body" Autonomous System
----------------------------------------------------------------------
 Profile: Intel Core i5-12450H | RTX 3050 (0% GPU Utilization Policy)
 Brain:   Google AI Studio Gemini API (Free Tier Zero-Cost)
 Safety:  Tiered Gate (READ: Auto | REVERSIBLE: Audited | IRREVERSIBLE: Y/N)
======================================================================
"""

HELP_TEXT = """
Available Commands:
  /help         - Show this help message
  /clear        - Reset current conversation context
  /tools        - List registered local tools and their safety tiers
  /status       - Show hardware, connection, and memory status
  /vault        - Inspect stored Obsidian Markdown notes and knowledge graph
  /recall <q>   - Test hybrid vector search + 2-hop graph expansion
  /apikey       - Enter or update Gemini API key interactively
  exit / quit   - Shutdown Friday session
"""


def prompt_for_api_key() -> str:
    """Prompt the user interactively for an API key if not set in .env."""
    if not sys.stdin.isatty():
        return ""

    print("\n[!] No GEMINI_API_KEY detected in .env.")
    print("    You can get a free key at: https://aistudio.google.com/")
    try:
        key = input("Enter your Gemini API Key (or press Enter to skip): ").strip()
        if key and key.lower() not in ("exit", "quit", "q"):
            # Optionally write to .env
            env_path = os.path.join(os.path.dirname(__file__), ".env")
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if "GEMINI_API_KEY=" in content:
                    new_content = ""
                    for line in content.splitlines():
                        if line.startswith("GEMINI_API_KEY="):
                            new_content += f"GEMINI_API_KEY={key}\n"
                        else:
                            new_content += line + "\n"
                    with open(env_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                else:
                    with open(env_path, "a", encoding="utf-8") as f:
                        f.write(f"\nGEMINI_API_KEY={key}\n")
            os.environ["GEMINI_API_KEY"] = key
            print("Saved key to .env and loaded for this session.\n")
            return key
    except (KeyboardInterrupt, EOFError):
        pass
    return ""


def main() -> None:
    """Run Friday's interactive CLI loop."""
    load_dotenv()
    print(BANNER)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        api_key = prompt_for_api_key()

    provider = GeminiProvider(api_key=api_key if api_key else None)
    gate = PermissionGate()
    agent = FridayAgent(gemini_provider=provider, permission_gate=gate)

    if provider.is_configured():
        print(f"Connected to Cloud Brain ({provider.model_name}). Friday is online.")
    else:
        print("Running in offline stub mode. Cloud Brain requires GEMINI_API_KEY.")

    print("Type your message or '/help' for commands. Type 'exit' to quit.\n")

    while True:
        try:
            user_input = input("friday> ").strip()
            if not user_input:
                continue

            # Command routing
            lower_input = user_input.lower()
            if lower_input in ("exit", "quit", "q"):
                print("\nShutting down Friday. Good luck with your studies!")
                break

            if lower_input == "/help":
                print(HELP_TEXT)
                continue

            if lower_input == "/clear":
                agent.reset_conversation()
                print("Conversation context has been reset.\n")
                continue

            if lower_input == "/tools":
                tools = agent.list_tools()
                if not tools:
                    print("No tools registered yet. (Tools will be added in Phases 2-4)\n")
                else:
                    print("\nRegistered Tools:")
                    for t in tools:
                        print(f"  - {t['name']} [{t['tier']}]: {t['description']}")
                    print()
                continue

            if lower_input == "/status":
                v_stats = agent.memory.graph_store.stats()
                print("\n[System Status]")
                print(f"  - Cloud Brain Model: {provider.model_name}")
                print(f"  - Brain Online:      {provider.is_configured()}")
                print(f"  - GPU Utilization:   0% (Enforced)")
                print(f"  - Obsidian Notes:    {len(agent.memory.list_all_titles())}")
                print(f"  - Vector Embeddings: {agent.memory.vector_store.count()}")
                print(f"  - Graph Nodes/Edges: {v_stats['total_nodes']}/{v_stats['total_edges']}")
                print(f"  - Registered Tools:  {len(agent.tools)}")
                print(f"  - Audit Log Count:   {len(gate.audit_log)}\n")
                continue

            if lower_input == "/vault":
                titles = agent.memory.list_all_titles()
                v_stats = agent.memory.graph_store.stats()
                print("\n[Obsidian Vault Overview]")
                print(f"Location: {agent.memory.vault.vault_dir}")
                print(f"Knowledge Graph: {v_stats['total_nodes']} nodes, {v_stats['total_edges']} connections\n")
                if not titles:
                    print("  No notes in vault yet. Try saying: 'remember: My Title - Content with [[Link]]'\n")
                else:
                    for t in titles:
                        print(f"  - [[{t}]]")
                    print()
                continue

            if lower_input.startswith("/recall"):
                query = user_input[7:].strip()
                if not query:
                    print("Usage: /recall <search query>\n")
                    continue
                results = agent.memory.recall(query=query, top_k=2, max_hops=2)
                print("\n" + "=" * 60)
                print(f"HYBRID RECALL RESULTS for: '{query}'")
                print("=" * 60)
                if results["direct_matches"]:
                    print("\n[Semantic Vector Matches]:")
                    for m in results["direct_matches"]:
                        print(f"  - [[{m['title']}]] (Similarity: {m['score']})")
                        print(f"    Content: {m['content'][:120]}...\n")
                else:
                    print("No direct vector matches found.")

                if results["graph_context"]:
                    print("[2-Hop Knowledge Graph Connections]:")
                    for g in results["graph_context"]:
                        print(f"  - [[{g['title']}]] ({g['distance_hops']}-hop distance)")
                    print()
                print("=" * 60 + "\n")
                continue

            if lower_input == "/apikey":
                new_key = prompt_for_api_key()
                if new_key:
                    provider.set_api_key(new_key)
                    print(f"Cloud Brain updated and online with {provider.model_name}.\n")
                continue

            # Process prompt through agent
            print("\nFriday is thinking...", end="\r", flush=True)
            response = agent.process(user_input)
            # Clear status line and print response
            print(" " * 30, end="\r")
            print(f"Friday:\n{response}\n")

        except KeyboardInterrupt:
            print("\n\nSession interrupted. Type 'exit' to quit.")
        except EOFError:
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()
