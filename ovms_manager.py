#!/usr/bin/env python3
"""
OpenVINO Model Server Configuration Manager

This script manages the ovms_config.json file and reloads the configuration
via the OpenVINO Model Server API.

Usage:
    python ovms_manager.py add <model_path> [--name <model_name>]
    python ovms_manager.py remove <model_name>
    python ovms_manager.py list
    python ovms_manager.py reload

Examples:
    python ovms_manager.py add /models/ov/mistral/llama-2-7b-chat
    python ovms_manager.py add /models/ov/mistral/phi-3-mini --name phi3-mini
    python ovms_manager.py add /models/ov/mistral/ministral --name ministral --llm
    python ovms_manager.py remove llama-2-7b-chat
    python ovms_manager.py list
    python ovms_manager.py reload
"""

import argparse
import json
import os
import sys
from pathlib import Path
import requests
from typing import Dict, List, Optional


class OVMSConfigManager:
    def __init__(self, config_path: str = "ovms_config.json", server_url: str = "http://localhost:8000", 
                 interactive: bool = True):
        self.config_path = Path(config_path)
        self.server_url = server_url
        self.interactive = interactive
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load the OVMS configuration file."""
        if not self.config_path.exists():
            # Create default config if it doesn't exist
            default_config = {
                "model_config_list": []
            }
            self._save_config(default_config)
            return default_config
        
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {self.config_path}: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error reading {self.config_path}: {e}")
            sys.exit(1)
    
    def _save_config(self, config: Dict) -> None:
        """Save the configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"✓ Configuration saved to {self.config_path}")
        except Exception as e:
            print(f"Error saving configuration: {e}")
            sys.exit(1)
    
    def _extract_model_name_from_path(self, model_path: str) -> str:
        """Extract model name from path."""
        return Path(model_path).name
    
    def _graph_exists(self, graph_name: str) -> bool:
        """Check if a graph with the given name already exists."""
        for graph in self.config.get("mediapipe_config_list", []):
            if graph.get("name") == graph_name:
                return True
        return False
    
    def _model_exists(self, model_name: str) -> bool:
        """Check if a model with the given name already exists."""
        for model in self.config.get("model_config_list", []):
            if model.get("config", {}).get("name") == model_name:
                return True
        return False
    
    def add_model(self, model_path: str, model_name: Optional[str] = None, 
                  is_llm: bool = False) -> None:
        """Add a model to the configuration."""
        # Validate model path
        if not Path(model_path).exists():
            print(f"Warning: Model path {model_path} does not exist")
            if self.interactive:
                response = input("Continue anyway? [y/N]: ")
                if response.lower() not in ['y', 'yes']:
                    print("Aborted.")
                    return
            else:
                print("Non-interactive mode: continuing anyway...")
        
        # Generate model name if not provided
        if not model_name:
            model_name = self._extract_model_name_from_path(model_path)
        
        # Check if model already exists (check both models and graphs)
        if self._model_exists(model_name) or self._graph_exists(model_name):
            print(f"Error: Model/Graph '{model_name}' already exists in configuration")
            print("Use 'remove' command first or specify a different name with --name")
            return
        
        if is_llm:
            # Create LLM graph configuration
            graph_config = {
                "name": model_name,
                "graph_path": "/models/ov/server/graph.pbtxt"
            }
            
            # Add model configuration for the LLM
            model_config = {
                "config": {
                    "name": f"{model_name}_model",
                    "base_path": model_path
                }
            }
            
            # Add to configuration
            if "model_config_list" not in self.config:
                self.config["model_config_list"] = []
            if "mediapipe_config_list" not in self.config:
                self.config["mediapipe_config_list"] = []
            
            self.config["model_config_list"].append(model_config)
            self.config["mediapipe_config_list"].append(graph_config)
            
            print(f"✓ Added LLM graph '{model_name}' with model '{model_name}_model'")
            print(f"  Path: {model_path}")
            
        else:
            # Create regular model configuration
            model_config = {
                "config": {
                    "name": model_name,
                    "base_path": model_path
                }
            }
            
            # Add to configuration
            if "model_config_list" not in self.config:
                self.config["model_config_list"] = []
            
            self.config["model_config_list"].append(model_config)
            
            print(f"✓ Added model '{model_name}' with path '{model_path}'")
        
        self._save_config(self.config)
    
    def remove_model(self, model_name: str) -> None:
        """Remove a model or graph from the configuration by name."""
        removed_items = []
        
        # Remove from model_config_list
        if "model_config_list" in self.config:
            original_count = len(self.config["model_config_list"])
            self.config["model_config_list"] = [
                model for model in self.config["model_config_list"]
                if model.get("config", {}).get("name") != model_name and 
                   model.get("config", {}).get("name") != f"{model_name}_model"
            ]
            new_count = len(self.config["model_config_list"])
            if original_count > new_count:
                removed_items.append("model")
        
        # Remove from mediapipe_config_list
        if "mediapipe_config_list" in self.config:
            original_count = len(self.config["mediapipe_config_list"])
            self.config["mediapipe_config_list"] = [
                graph for graph in self.config["mediapipe_config_list"]
                if graph.get("name") != model_name
            ]
            new_count = len(self.config["mediapipe_config_list"])
            if original_count > new_count:
                removed_items.append("graph")
        
        if not removed_items:
            print(f"Error: Model/Graph '{model_name}' not found in configuration")
            self.list_models()
            return
        
        self._save_config(self.config)
        print(f"✓ Removed {'/'.join(removed_items)} '{model_name}' from configuration")
    
    def list_models(self) -> None:
        """List all models and graphs in the configuration."""
        models = self.config.get("model_config_list", [])
        graphs = self.config.get("mediapipe_config_list", [])
        
        if not models and not graphs:
            print("No models or graphs configured")
            return
        
        total_items = len(models) + len(graphs)
        print(f"Configured items ({total_items}):")
        print("-" * 80)
        
        item_num = 1
        
        # List regular models
        for model in models:
            config = model.get("config", {})
            name = config.get("name", "Unknown")
            path = config.get("base_path", "Unknown")
            
            # Check if this is part of an LLM graph
            is_llm_model = name.endswith("_model") and any(
                f"{graph.get('name')}_model" == name 
                for graph in graphs
            )
            
            if not is_llm_model:
                print(f"{item_num:2d}. {name} (Model)")
                print(f"    Path: {path}")
                print()
                item_num += 1
        
        # List graphs (LLMs)
        for graph in graphs:
            graph_name = graph.get("name", "Unknown")
            model_name = f"{graph_name}_model"
            
            # Find the corresponding model
            model_path = "Unknown"
            for model in models:
                if model.get("config", {}).get("name") == model_name:
                    model_path = model.get("config", {}).get("base_path", "Unknown")
                    break
            
            print(f"{item_num:2d}. {graph_name} (LLM Graph)")
            print(f"    Path: {model_path}")
            print(f"    Model: {model_name}")
            print()
            item_num += 1
    
    def reload_config(self) -> None:
        """Reload the configuration via OVMS API."""
        try:
            url = f"{self.server_url}/v1/config/reload"
            print(f"Reloading configuration via {url}...")
            
            response = requests.post(url, timeout=30)
            
            if response.status_code == 200:
                print("✓ Configuration reloaded successfully")
                try:
                    result = response.json()
                    if result:
                        print(f"Server response: {result}")
                except:
                    pass
            else:
                print(f"✗ Failed to reload configuration")
                print(f"Status code: {response.status_code}")
                print(f"Response: {response.text}")
                
        except requests.exceptions.ConnectionError:
            print(f"✗ Could not connect to OVMS server at {self.server_url}")
            print("Make sure the OpenVINO Model Server is running")
        except requests.exceptions.Timeout:
            print("✗ Request timed out")
        except Exception as e:
            print(f"✗ Error reloading configuration: {e}")
    
    def status(self) -> None:
        """Check server status and list loaded models."""
        try:
            # Check server status
            url = f"{self.server_url}/v1/config"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                print("✓ OVMS server is running")
                try:
                    config = response.json()
                    models = config.get("model_config_list", [])
                    print(f"Loaded models: {len(models)}")
                    for model in models:
                        name = model.get("config", {}).get("name", "Unknown")
                        print(f"  - {name}")
                except:
                    print("Could not parse server response")
            else:
                print(f"✗ Server returned status code: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print(f"✗ OVMS server not reachable at {self.server_url}")
        except Exception as e:
            print(f"✗ Error checking server status: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="OpenVINO Model Server Configuration Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s add /models/ov/mistral/llama-2-7b-chat
  %(prog)s add /models/ov/mistral/phi-3-mini --name phi3-mini
  %(prog)s add /models/ov/mistral/ministral --name ministral --llm
  %(prog)s remove llama-2-7b-chat
  %(prog)s list
  %(prog)s reload
  %(prog)s status"""
    )
    
    parser.add_argument(
        "--config", "-c",
        default="ovms_config.json",
        help="Path to OVMS configuration file (default: ovms_config.json)"
    )
    
    parser.add_argument(
        "--server", "-s",
        default="http://localhost:8000",
        help="OVMS server URL (default: http://localhost:8000)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Add command
    add_parser = subparsers.add_parser("add", help="Add a model or LLM graph to the configuration")
    add_parser.add_argument("path", help="Path to the model directory")
    add_parser.add_argument("--name", "-n", help="Model name (default: extracted from path)")
    add_parser.add_argument("--llm", action="store_true",
                           help="Add as LLM graph (MediaPipe pipeline)")
    
    # Remove command
    remove_parser = subparsers.add_parser("remove", help="Remove a model or graph from the configuration")
    remove_parser.add_argument("name", help="Name of the model/graph to remove")
    
    # List command
    subparsers.add_parser("list", help="List all configured models and graphs")
    
    # Reload command
    subparsers.add_parser("reload", help="Reload the configuration on the server")
    
    # Status command
    subparsers.add_parser("status", help="Check server status and loaded models")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Create manager instance
    manager = OVMSConfigManager(args.config, args.server)
    
    # Execute command
    if args.command == "add":
        manager.add_model(args.path, args.name, args.llm)
    elif args.command == "remove":
        manager.remove_model(args.name)
    elif args.command == "list":
        manager.list_models()
    elif args.command == "reload":
        manager.reload_config()
    elif args.command == "status":
        manager.status()


if __name__ == "__main__":
    main()