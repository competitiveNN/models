from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import argparse

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Test LLM with transformers")
parser.add_argument(
    "--model-name",
    type=str,
    default="Intel/GLM-4.7-Flash-int4-AutoRound",
    help="Model name or path to load (default: Intel/GLM-4.7-Flash-int4-AutoRound)"
)
parser.add_argument(
    "--prompt",
    type=str,
    default="hello",
    help="User prompt to send to the model (default: hello)"
)
args = parser.parse_args()

# Load the model on the available device(s)
model_name = args.model_name
model = AutoModelForCausalLM.from_pretrained(
    model_name, dtype="auto", device_map="auto"
)
messages = [{"role": "user", "content": args.prompt}]
tokenizer = AutoTokenizer.from_pretrained(model_name)
inputs = tokenizer.apply_chat_template(
    messages,
    tokenize=True,
    add_generation_prompt=True,
    return_dict=True,
    return_tensors="pt",
)
inputs = inputs.to(model.device)
generated_ids = model.generate(**inputs, max_new_tokens=128, do_sample=False)
output_text = tokenizer.decode(generated_ids[0][inputs.input_ids.shape[1]:])
print(output_text)