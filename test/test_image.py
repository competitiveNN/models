import argparse
import base64
import os
from openai import OpenAI

# Configuration (now handled by CLI arguments)
# These constants are kept for reference but overridden by CLI args
API_BASE = "http://localhost:8000/v1"
API_KEY = "abc"  # Local servers often don't enforce key, but keeping format
MODEL_NAME = "gemma-4b" # Placeholder based on your config, adjust if needed
IMAGE_PATH = "image.png"
PROMPT = "describe the image"

def encode_image(image_path):
    """Encodes a local image file to base64 string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def parse_arguments():
    """Parse command line arguments for model parameters."""
    parser = argparse.ArgumentParser(description="Test OpenAI-compatible API with configurable model parameters")
    
    # Basic configuration
    parser.add_argument("--api-base", default="http://localhost:8000/v1", 
                       help="API base URL (default: http://localhost:8000/v1)")
    parser.add_argument("--api-key", default="abc", 
                       help="API key (default: abc)")
    parser.add_argument("--model", default="gemma-4b", 
                       help="Model name (default: gemma-4b)")
    parser.add_argument("--image", default="image.png", 
                       help="Path to image file (default: image.png)")
    parser.add_argument("--prompt", default="describe the image", 
                       help="Text prompt (default: 'describe the image')")
    
    # Model parameters
    parser.add_argument("--temperature", type=float, default=0.7, 
                       help="Sampling temperature (0.0-2.0, default: 0.7)")
    parser.add_argument("--max-tokens", type=int, default=32768, 
                       help="Maximum tokens to generate (default: 32768)")
    parser.add_argument("--top-p", type=float, default=1.0, 
                       help="Nucleus sampling parameter (0.0-1.0, default: 1.0)")
    parser.add_argument("--frequency-penalty", type=float, default=0.0, 
                       help="Frequency penalty (-2.0 to 2.0, default: 0.0)")
    parser.add_argument("--presence-penalty", type=float, default=0.0, 
                       help="Presence penalty (-2.0 to 2.0, default: 0.0)")
    parser.add_argument("--seed", type=int, 
                       help="Random seed for reproducible outputs")
    parser.add_argument("--stream", action="store_true", 
                       help="Enable streaming response")
    
    return parser.parse_args()

def main():
    # Parse command line arguments
    args = parse_arguments()
    
    if not os.path.exists(args.image):
        print(f"Error: Image file '{args.image}' not found.")
        return

    # Initialize the client pointing to the local API
    client = OpenAI(
        base_url=args.api_base,
        api_key=args.api_key,
    )

    try:
        # Encode the image
        base64_image = encode_image(args.image)

        # Prepare the request parameters
        request_params = {
            "model": args.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": args.prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            "max_tokens": args.max_tokens,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "frequency_penalty": args.frequency_penalty,
            "presence_penalty": args.presence_penalty,
            "stream": args.stream,
        }
        
        # Add optional parameters if provided
        if args.seed is not None:
            request_params["seed"] = args.seed

        # Create the chat completion request
        response = client.chat.completions.create(**request_params)

        # Handle streaming vs non-streaming response
        if args.stream:
            print("Response (streaming):")
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    print(chunk.choices[0].delta.content, end="", flush=True)
            print()  # New line after streaming
        else:
            # Print the response content
            print("Response:")
            print(response.choices[0].message.content)

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
