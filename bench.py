import asyncio
import time
import argparse
from openai import AsyncOpenAI, OpenAI
import sys

# A prompt that reliably generates long output
DEFAULT_PROMPT = "Write a comprehensive essay about the history of artificial intelligence, covering early logic machines to modern large language models. Be detailed."

async def make_request(client, model, prompt, max_tokens):
    try:
        start_time = time.perf_counter()
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            timeout=600 # Long timeout for large context
        )
        end_time = time.perf_counter()
        
        latency = end_time - start_time
        tokens = response.usage.completion_tokens if response.usage else 0
        
        return {
            "latency": latency,
            "tokens": tokens,
            "success": True,
            "error_msg": None
        }
    except Exception as e:
        return {
            "latency": 0,
            "tokens": 0,
            "success": False,
            "error_msg": str(e)
        }

def list_models(url, api_key):
    try:
        client = OpenAI(api_key=api_key, base_url=url)
        models = client.models.list()
        print("\nAvailable Models:")
        for model in models.data:
            print(f"  - {model.id}")
        print()
    except Exception as e:
        print(f"Failed to list models: {e}")

async def run_benchmark_session(client, model, num_requests, concurrency, max_tokens, quiet=False):
    if not quiet:
        print(f"Testing Concurrency: {concurrency:5d} ...", end=" ", flush=True)
    
    semaphore = asyncio.Semaphore(concurrency)
    
    async def sem_request():
        async with semaphore:
            return await make_request(client, model, DEFAULT_PROMPT, max_tokens)
    
    start_time = time.perf_counter()
    tasks = [sem_request() for _ in range(num_requests)]
    results = await asyncio.gather(*tasks)
    end_time = time.perf_counter()
    
    total_wall_time = end_time - start_time
    successful_requests = sum(1 for r in results if r["success"])
    total_tokens = sum(r["tokens"] for r in results if r["success"])
    
    tps = total_tokens / total_wall_time if total_wall_time > 0 else 0
    error_rate = (num_requests - successful_requests) / num_requests
    
    if not quiet:
        print(f"TPS: {tps:8.2f} | Error Rate: {error_rate:7.2%}")
        
    return {
        "concurrency": concurrency,
        "tps": tps,
        "error_rate": error_rate,
        "successful_requests": successful_requests,
        "total_tokens": total_tokens,
        "total_wall_time": total_wall_time
    }

async def optimize_concurrency(url, api_key, model, max_tokens):
    client = AsyncOpenAI(api_key=api_key, base_url=url)
    print(f"Optimizing concurrency for {model} at {url}...")
    
    all_results = {} # concurrency -> result
    
    # Phase 1: Exponential Exploration (Powers of 2)
    curr_c = 1
    best_c = 1
    while curr_c <= 128:
        # Use enough requests to get stable results
        num_requests = max(curr_c * 2, 4)
        res = await run_benchmark_session(client, model, num_requests, curr_c, max_tokens)
        all_results[curr_c] = res
        
        if res["error_rate"] > 0.15:
            print("Stopping: Error rate too high.")
            break
            
        if res["tps"] > all_results[best_c]["tps"] * 1.02: # 2% improvement threshold
            best_c = curr_c
        elif curr_c > 1 and res["tps"] < all_results[best_c]["tps"] * 0.95:
            print(f"Stopping: TPS dropped from {all_results[best_c]['tps']:.2f} to {res['tps']:.2f}")
            break
        
        curr_c *= 2

    # Phase 2: Exploitation (Refinement around the peak)
    print("\nStarting refinement phase for best parameters...")
    
    while True:
        sorted_c = sorted(all_results.keys())
        best_idx = sorted_c.index(best_c)
        
        # Identify bounds for refinement
        lower_bound = sorted_c[best_idx-1] if best_idx > 0 else None
        upper_bound = sorted_c[best_idx+1] if best_idx < len(sorted_c) - 1 else None
        
        points_to_test = []
        if lower_bound is not None and (best_c - lower_bound) > 1:
            points_to_test.append((lower_bound + best_c) // 2)
        if upper_bound is not None and (upper_bound - best_c) > 1:
            points_to_test.append((best_c + upper_bound) // 2)
            
        if not points_to_test:
            break
            
        found_better = False
        for c in points_to_test:
            if c not in all_results:
                res = await run_benchmark_session(client, model, max(c * 2, 4), c, max_tokens)
                all_results[c] = res
                if res["tps"] > all_results[best_c]["tps"] and res["error_rate"] <= 0.1:
                    best_c = c
                    found_better = True
        
        if not found_better:
            break

    final_best = all_results[best_c]
    print("\n" + "="*40)
    print(f"Optimization Finished")
    print(f"Best Concurrency Found: {best_c}")
    print(f"Maximum TPS Achieved:   {final_best['tps']:.2f}")
    print("="*40)

async def find_max_context(url, api_key, model):
    client = AsyncOpenAI(api_key=api_key, base_url=url)
    print(f"Discovering maximum context length for {model}...")
    
    def get_dummy_prompt(tokens):
        # approx 4 chars per token + safety margin
        return "x " * tokens

    low = 1024
    high = 1048576 
    last_success = 0
    
    # Step 1: Exponential search for upper bound
    current = 1024
    while current <= high:
        print(f"Testing context length: {current:7d} tokens ...", end=" ", flush=True)
        res = await make_request(client, model, get_dummy_prompt(current), 1)
        
        if res["success"]:
            print("OK")
            last_success = current
            current *= 2
        else:
            print(f"FAILED (Error: {res['error_msg'][:60]}...)")
            high = current
            break
    
    # Step 2: Binary search for precision
    low = last_success
    while low <= high and (high - low) > 1024:
        mid = (low + high) // 2
        print(f"Testing context length: {mid:7d} tokens ...", end=" ", flush=True)
        res = await make_request(client, model, get_dummy_prompt(mid), 1)
        
        if res["success"]:
            print("OK")
            low = mid + 1
            last_success = mid
        else:
            print("FAILED")
            high = mid - 1
            
    print("\n" + "="*40)
    print(f"Max Context Discovery Finished")
    print(f"Approximate Max Context: ~{last_success} tokens")
    print("="*40)

async def main_benchmark(url, api_key, model, num_requests, concurrency, max_tokens):
    client = AsyncOpenAI(api_key=api_key, base_url=url)
    res = await run_benchmark_session(client, model, num_requests, concurrency, max_tokens, quiet=True)
    
    print("\n" + "="*40)
    print(f"Results for {url}")
    print(f"Concurrency: {concurrency}")
    print(f"Total Wall Time: {res['total_wall_time']:.2f}s")
    print(f"Successful Requests: {res['successful_requests']}/{num_requests}")
    print(f"Total Tokens Generated: {res['total_tokens']}")
    print(f"TPS (Total Tokens Per Second): {res['tps']:.2f}")
    print("="*40)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple OpenAI API TPS Benchmark")
    parser.add_argument("--url", default="http://localhost:8000/v1", help="API URL")
    parser.add_argument("--api-key", default="abc", help="API Key")
    parser.add_argument("--model", default="qwen3-14b", help="Model name")
    parser.add_argument("--requests", type=int, default=1, help="Total requests")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrency")
    parser.add_argument("--max-tokens", type=int, default=250, help="Max tokens to generate")
    parser.add_argument("--list", action="store_true", help="List available models and exit")
    parser.add_argument("--optimize", action="store_true", help="Find the best concurrency")
    parser.add_argument("--context", action="store_true", help="Find max context length")
    
    args = parser.parse_args()
    
    try:
        if args.list:
            list_models(args.url, args.api_key)
        elif args.optimize:
            asyncio.run(optimize_concurrency(args.url, args.api_key, args.model, args.max_tokens))
        elif args.context:
            asyncio.run(find_max_context(args.url, args.api_key, args.model))
        else:
            asyncio.run(main_benchmark(args.url, args.api_key, args.model, args.requests, args.concurrency, args.max_tokens))
    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
