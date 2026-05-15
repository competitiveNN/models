import asyncio
import time
import argparse
from openai import AsyncOpenAI, OpenAI
import sys

PROMPTS = [
"Write a comprehensive essay about the history of artificial intelligence, covering early logic machines to modern large language models. Be detailed.",
"Explain in depth how solar panels convert sunlight into electricity, including the physics of photovoltaic cells and their real-world efficiency.",
"Describe the process of fermentation in detail, covering the biochemistry behind how yeast transforms sugars into alcohol and carbon dioxide.",
"Provide a thorough analysis of the economic factors that led to the Great Depression of 1929, and discuss the policy responses that followed.",
"Write a detailed overview of how the human immune system identifies and fights off viral infections, including the roles of T cells and antibodies.",
"Discuss the history and evolution of the English language, from its Germanic roots through the Norman Conquest to modern-day usage.",
"Explain the principles behind quantum computing, including qubits, superposition, and entanglement, and how they differ from classical computers.",
"Describe the geological processes that shape mountain ranges, including plate tectonics, erosion, and volcanic activity.",
"Write a detailed essay on the causes and consequences of the French Revolution, covering social, political, and economic factors.",
"Explain how photosynthesis works at the molecular level, including light-dependent reactions and the Calvin cycle.",
"Describe the history and development of the railroad system in the United States, and its impact on westward expansion.",
"Provide a comprehensive analysis of the biodiversity crisis, including habitat loss, climate change, and invasive species.",
"Write about the evolution of jazz music from its roots in blues and African rhythms to modern improvisation.",
"Explain the mechanisms of antibiotic resistance in bacteria and the public health challenges it presents.",
"Describe the design principles behind suspension bridges, including tension, compression, and materials science.",
"Discuss the philosophical foundations of utilitarianism, from Bentham to Mill, and its modern applications.",
"Write a detailed account of the Space Race between the United States and Soviet Union during the Cold War.",
"Explain how CRISPR-Cas9 gene editing works and its potential applications in medicine and agriculture.",
"Describe the hydrological cycle in detail, including evaporation, condensation, precipitation, and runoff.",
"Provide a thorough explanation of how the human digestive system breaks down food from mouth to intestine.",
"Write about the role of the printing press in the spread of the Protestant Reformation across Europe.",
"Explain the principles of thermodynamics, including the laws of thermodynamics and their real-world applications.",
"Describe the migration patterns of monarch butterflies and the biological mechanisms that guide their journey.",
"Discuss the impact of colonialism on indigenous cultures in Africa, including cultural displacement and economic exploitation.",
"Write a comprehensive overview of the development of the internet from ARPANET to the World Wide Web.",
"Explain how machine learning algorithms learn from data, covering supervised, unsupervised, and reinforcement learning.",
"Describe the process of DNA replication and the role of enzymes in ensuring accurate genetic information transfer.",
"Provide a detailed analysis of the causes of World War I, including militarism, alliances, imperialism, and nationalism.",
"Write about the scientific contributions of Marie Curie, including her work on radioactivity and its legacy.",
"Explain how the circulatory system delivers oxygen and nutrients to cells throughout the human body.",
"Describe the art and architecture of ancient Egypt, including pyramids, hieroglyphics, and religious practices.",
"Discuss the economic theory of supply and demand and how market equilibrium is reached in competitive markets.",
"Write a detailed essay on the challenges of clean water access in developing countries and potential solutions.",
"Explain the role of mitochondria in cellular respiration and energy production in eukaryotic cells.",
"Describe the history of the Roman Empire, from its founding to its fall, including political and military strategies.",
"Provide a comprehensive explanation of how climate change affects ocean ecosystems, including coral bleaching and acidification.",
"Write about the development of the theory of relativity by Albert Einstein and its implications for physics.",
"Explain how the human nervous system transmits signals from sensory organs to the brain for processing.",
"Describe the cultural significance of the Renaissance in Europe, including advances in art, science, and philosophy.",
"Discuss the ethical considerations of autonomous vehicles and the decision-making frameworks being developed.",
"Write a detailed account of the Harlem Renaissance and its impact on African American art, literature, and music.",
"Explain how wind turbines generate electricity, including aerodynamics, generator principles, and grid integration.",
"Describe the life cycle of a star, from nebula formation to supernova or white dwarf, including fusion processes.",
"Provide a thorough analysis of the spread of misinformation on social media and its effects on democratic processes.",
"Write about the development of antibiotics and the ongoing challenge of treating resistant bacterial infections.",
"Explain how the human skeletal system provides support, protection, and movement for the body.",
"Describe the history of apartheid in South Africa, including its origins, enforcement, and eventual dismantling.",
"Discuss the mathematical foundations of cryptography, including public-key and symmetric encryption methods.",
"Write a comprehensive essay on the relationship between diet, exercise, and chronic disease prevention.",
"Explain how the greenhouse effect works and why certain gases contribute more to global warming than others.",
"Describe the engineering challenges of building skyscrapers, including foundations, wind resistance, and materials.",
"Provide a detailed analysis of the Amazon rainforest ecosystem and the threats posed by deforestation.",
"Write about the history of vaccination, from Edward Jenner's smallpox vaccine to modern mRNA technology.",
"Explain how the human endocrine system regulates bodily functions through hormones and feedback loops.",
"Describe the development of the atomic bomb during World War II, including the Manhattan Project and its aftermath.",
"Discuss the role of symbiosis in evolution, including mutualism, commensalism, and parasitism with examples.",
"Write a detailed account of the Silk Road and its role in cultural and economic exchange between East and West.",
"Explain how electric motors work, including electromagnetic induction and the conversion of electrical to mechanical energy.",
"Describe the biogeochemical cycles of carbon, nitrogen, and phosphorus and their importance in ecosystems.",
"Provide a comprehensive overview of the history of cinema, from early motion pictures to modern digital filmmaking.",
"Write about the physics of black holes, including event horizons, singularity, and Hawking radiation.",
"Explain how the human muscular system enables movement through the interaction of muscle fibers and motor neurons.",
"Describe the political philosophy of democracy, including direct and representative systems and their strengths and weaknesses.",
"Discuss the impact of the Industrial Revolution on urbanization, labor conditions, and social class structures.",
"Write a detailed analysis of the biodiversity of coral reef ecosystems and the species that depend on them.",
"Explain how the human respiratory system extracts oxygen from air and expels carbon dioxide through gas exchange.",
"Describe the history and significance of the Magna Carta in establishing principles of limited government.",
"Provide a thorough explanation of how blockchain technology works and its potential applications beyond cryptocurrency.",
"Write about the evolution of human language, including theories of its origin and how it differs from animal communication.",
"Explain how radar and sonar systems use electromagnetic or sound waves to detect objects and measure distance.",
"Describe the cultural and historical significance of the ancient city of Constantinople and its role in bridging East and West.",
"Discuss the mechanisms of memory formation in the brain, including short-term and long-term memory processes.",
"Write a comprehensive essay on the challenges of sustainable agriculture in the face of a growing global population.",
"Explain how the human reproductive system functions, including gamete production, fertilization, and embryonic development.",
"Describe the history of the samurai in Japan, including their role in feudal society and their philosophical code.",
"Provide a detailed analysis of how deforestation contributes to climate change and loss of biodiversity.",
"Write about the development of the polio vaccine and the global effort to eradicate the disease through vaccination.",
"Explain how the human lymphatic system supports immune function and maintains fluid balance in the body.",
"Describe the engineering principles behind dams and reservoirs, including structural design and environmental impact.",
"Discuss the philosophical debate between rationalism and empiricism and its influence on modern scientific methodology.",
"Write a detailed account of the Meiji Restoration in Japan and its transformation from feudal society to industrial power.",
"Explain how electrolysis separates water into hydrogen and oxygen and its applications in energy production.",
"Describe the ecological relationships in a temperate deciduous forest, including food webs and nutrient cycling.",
"Provide a comprehensive explanation of how the human urinary system filters blood and maintains homeostasis.",
"Write about the history of computing, from Charles Babbage's analytical engine to modern cloud computing architectures.",
"Explain how fiber optics transmit data using total internal reflection and their advantages over copper cables.",
"Describe the history and impact of the Transatlantic slave trade on African societies and the Americas.",
"Discuss the role of mycorrhizal networks in forests and how trees communicate and share resources underground.",
"Write a detailed analysis of the development of the theory of plate tectonics and its evidence base.",
"Explain how the human integumentary system protects the body through skin, hair, and nails.",
"Describe the history of the Ottoman Empire, from its founding to its dissolution after World War I.",
"Provide a thorough explanation of how virtual reality headsets create immersive visual experiences through optics and software.",
"Write about the philosophical concept of the social contract and its influence on modern democratic governance.",
"Explain how the human excretory system removes metabolic waste products from the body through the kidneys.",
"Describe the life and achievements of Leonardo da Vinci, including his contributions to art, science, and engineering.",
"Discuss the mechanisms of platelet aggregation and blood clotting in wound healing and its clinical significance.",
"Write a comprehensive essay on the impact of microplastics on marine ecosystems and human health.",
"Explain how the human vestibular system maintains balance and spatial orientation through semicircular canals and otoliths.",
"Describe the history of the Korean War, its causes, major battles, and lasting geopolitical consequences.",
"Provide a detailed analysis of how artificial light at night disrupts ecosystems and affects wildlife behavior.",
"Write about the development of penicillin and the antibiotic revolution in modern medicine.",
"Explain how the human visual system processes light through the eye and optic nerve to create visual perception.",
"Describe the cultural and historical significance of the ancient Inca Empire, including its engineering and administration.",
"Discuss the role of epigenetics in gene expression and how environmental factors can influence heritable traits.",
"Write a detailed account of the Partition of India in 1947 and its lasting impact on South Asian politics.",
"Explain how desalination plants convert seawater into freshwater using reverse osmosis and thermal distillation.",
"Describe the ecological importance of wetlands, including their role in water filtration, flood control, and biodiversity.",
"Provide a comprehensive analysis of how the COVID-19 pandemic reshaped global health systems and public policy.",
"Write about the history of the Women's Suffrage Movement and its impact on gender equality in democratic societies.",
"Explain how the human auditory system processes sound waves from the outer ear through the cochlea to the brain.",
"Describe the historical significance of the American Civil Rights Movement and its legacy in American society.",
"Discuss the mechanics of how earthquakes occur along fault lines and the factors that determine their magnitude.",
"Write a detailed essay on the ethical implications of genetic engineering in humans and its potential for eliminating diseases.",
"Explain how bioluminescence works in deep-sea organisms and the biochemical processes that produce light.",
"Describe the history and architecture of Gothic cathedrals in medieval Europe, including their construction techniques.",
"Provide a thorough analysis of how invasive species disrupt native ecosystems and the strategies used for management.",
"Write about the role of rivers in shaping civilizations, from ancient Egypt to modern hydroelectric power generation.",
"Explain the fundamental principles of object-oriented programming, including encapsulation, inheritance, and polymorphism.",
"Describe the journey of a photon from the Sun's core to Earth's surface and its energy transformations along the way.",
"Discuss the economic impact of automation on manufacturing jobs and the transition to knowledge-based economies.",
"Write about the chemistry of cooking, including Maillard reactions, caramelization, and the science behind flavor development.",
"Explain how the human skeletal system provides support, protection, and movement for the body.",
"Describe the history and significance of the ancient city of Constantinople and its role in bridging East and West.",
"Discuss the role of symbiosis in evolution, including mutualism, commensalism, and parasitism with examples.",
"Write a detailed account of the Silk Road and its role in cultural and economic exchange between East and West.",
"Explain how electric motors work, including electromagnetic induction and the conversion of electrical to mechanical energy.",
"Describe how echolocation enables bats and dolphins to navigate and hunt in low-visibility environments through sound wave analysis.",
"Explain the molecular mechanisms of long-term potentiation and its role in learning and memory formation.",
]

async def make_request(client, model, prompt, max_tokens):
    try:
        start_time = time.perf_counter()
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            timeout=600
        )
        end_time = time.perf_counter()
        latency = end_time - start_time
        tokens = response.usage.completion_tokens if response.usage else 0
        return {"latency": latency, "tokens": tokens, "success": True, "error_msg": None}
    except Exception as e:
        return {"latency": 0, "tokens": 0, "success": False, "error_msg": str(e)}

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
    async def sem_request(idx):
        async with semaphore:
            prompt = PROMPTS[idx % len(PROMPTS)]
            return await make_request(client, model, prompt, max_tokens)
    start_time = time.perf_counter()
    tasks = [sem_request(i) for i in range(num_requests)]
    results = await asyncio.gather(*tasks)
    end_time = time.perf_counter()
    total_wall_time = end_time - start_time
    successful_requests = sum(1 for r in results if r["success"])
    total_tokens = sum(r["tokens"] for r in results if r["success"])
    tps = total_tokens / total_wall_time if total_wall_time > 0 else 0
    error_rate = (num_requests - successful_requests) / num_requests
    if not quiet:
        print(f"TPS: {tps:8.2f} | Error Rate: {error_rate:7.2%}")
    return {"concurrency": concurrency, "tps": tps, "error_rate": error_rate, "successful_requests": successful_requests, "total_tokens": total_tokens, "total_wall_time": total_wall_time}

async def optimize_concurrency(url, api_key, model, max_tokens, start_concurrency=1):
    client = AsyncOpenAI(api_key=api_key, base_url=url)
    print(f"Optimizing concurrency for {model} at {url}...")
    all_results = {}
    curr_c = start_concurrency
    best_c = start_concurrency
    while curr_c <= 128:
        num_requests = max(curr_c * 2, 4)
        res = await run_benchmark_session(client, model, num_requests, curr_c, max_tokens)
        all_results[curr_c] = res
        if res["error_rate"] > 0.15:
            print("Stopping: Error rate too high.")
            break
        if res["tps"] > all_results[best_c]["tps"] * 1.02:
            best_c = curr_c
        elif curr_c > 1 and res["tps"] < all_results[best_c]["tps"] * 0.95:
            print(f"Stopping: TPS dropped from {all_results[best_c]['tps']:.2f} to {res['tps']:.2f}")
            break
        curr_c *= 2
    print("\nStarting refinement phase for best parameters...")
    while True:
        sorted_c = sorted(all_results.keys())
        best_idx = sorted_c.index(best_c)
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
        return "x " * tokens
    low = 1024
    high = 1048576
    last_success = 0
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
            asyncio.run(optimize_concurrency(args.url, args.api_key, args.model, args.max_tokens, args.concurrency))
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
