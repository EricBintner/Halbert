#!/usr/bin/env python3
"""
Merge all RAG data sources into a unified, deduplicated corpus.

Sources:
1. vendor_docs_full.jsonl (40 docs) - Vendor docs from wikis/man pages
2. tldr_man_pages.jsonl (481 docs) - HF TLDR summaries
3. unix_commands.jsonl (100 docs) - HF unix commands
4. arch_wiki.jsonl (2140 docs) - HF Arch Wiki
5. combined_all_output.jsonl (246 docs) - Instruction format data

Output: Merged, deduplicated RAG corpus in unified format
"""
import json
from pathlib import Path
from datetime import datetime


def convert_combined_all_output(input_path: Path, output_path: Path):
    """
    Convert combined_all_output.jsonl from instruction format to RAG format.
    
    Schema: {goal, commands, explanation, ...}
    -> {name, description, full_text, metadata}
    """
    docs = []
    with open(input_path, 'r') as f:
        for line in f:
            item = json.loads(line)
            goal = item.get('goal', '')
            explanation = item.get('explanation', '')
            commands = item.get('commands', [])
            
            # Build command text
            cmd_text = '\n'.join([
                f"{i+1}. {cmd.get('step', '')}\n   Command: {cmd.get('cmd', '')}"
                for i, cmd in enumerate(commands)
            ])
            
            full_text = f"Goal: {goal}\n\n{explanation}\n\nCommands:\n{cmd_text}"
            
            # Extract primary command for name
            name = 'linux_command'
            if commands:
                first_cmd = commands[0].get('cmd', '')
                words = first_cmd.split()
                if words:
                    name = words[0]
            
            docs.append({
                'name': name,
                'section': '',
                'description': goal[:200],
                'full_text': full_text,
                'metadata': {
                    'source_type': 'training_data',
                    'dataset': 'combined_all_output',
                    'trust': 'curated',
                    'os': item.get('os', 'linux'),
                    'distro': item.get('distro', 'ubuntu-22.04'),
                    'risk_level': item.get('risk_level', 'unknown')
                }
            })
    
    # Write converted format
    with open(output_path, 'w') as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')
    
    print(f"✓ Converted {len(docs)} docs from {input_path} to {output_path}")
    return len(docs)


def main():
    print("="*70)
    print("Merging all RAG data sources")
    print("="*70)
    
    # Setup paths
    data_dir = Path('data/linux')
    output_dir = data_dir / 'merged'
    output_dir.mkdir(exist_ok=True)
    
    # Convert combined_all_output first
    print("\n1. Converting combined_all_output.jsonl to RAG format...")
    converted_path = output_dir / 'combined_all_output_converted.jsonl'
    convert_combined_all_output(
        data_dir / 'commands' / 'combined_all_output.jsonl',
        converted_path
    )
    
    # Source files to merge
    sources = [
        data_dir / 'vendor-docs' / 'vendor_docs_full.jsonl',
        data_dir / 'hf-datasets' / 'tldr_man_pages.jsonl',
        data_dir / 'hf-datasets' / 'unix_commands.jsonl',
        data_dir / 'hf-datasets' / 'arch_wiki.jsonl',
        converted_path
    ]
    
    # Add NVIDIA docs if available
    nvidia_docs = data_dir / 'nvidia-docs' / 'nvidia_cuda_docs.jsonl'
    if nvidia_docs.exists():
        sources.append(nvidia_docs)
        print(f"\n   ✓ Including NVIDIA/CUDA documentation")
    
    print(f"\n2. Merging {len(sources)} data sources...")
    for src in sources:
        if src.exists():
            with open(src) as f:
                count = sum(1 for _ in f)
            print(f"   - {src.name}: {count} docs")
        else:
            print(f"   ✗ Missing: {src}")
    
    # Manual merge with deduplication
    print("\n3. Loading and deduplicating...")
    
    # Load all sources with progress
    all_docs = []
    source_counts = {}
    
    for i, src in enumerate(sources, 1):
        if src.exists():
            print(f"   [{i}/{len(sources)}] Loading {src.name}...", end=' ', flush=True)
            try:
                with open(src, 'r') as f:
                    docs = []
                    for line_num, line in enumerate(f, 1):
                        try:
                            docs.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            print(f"\n      WARNING: Line {line_num} parse error: {e}")
                    all_docs.extend(docs)
                    source_name = src.stem
                    source_counts[source_name] = len(docs)
                print(f"{len(docs)} docs")
            except Exception as e:
                print(f"\n      ERROR: {e}")
    
    print(f"\n   Total loaded: {len(all_docs)} documents")
    
    # Deduplicate by content hash
    print("   Deduplicating...", end=' ', flush=True)
    seen_hashes = set()
    deduped_docs = []
    
    for doc in all_docs:
        # Create hash from name + description + first 500 chars of full_text
        name = str(doc.get('name', ''))
        desc = str(doc.get('description', ''))
        text = str(doc.get('full_text', ''))[:500]
        content_hash = hash(name + desc + text)
        
        if content_hash not in seen_hashes:
            seen_hashes.add(content_hash)
            deduped_docs.append(doc)
    
    duplicates_removed = len(all_docs) - len(deduped_docs)
    print(f"{len(deduped_docs)} unique (removed {duplicates_removed} duplicates)")
    
    # Save merged corpus
    output_path = output_dir / 'rag_corpus_merged.jsonl'
    with open(output_path, 'w') as f:
        for doc in deduped_docs:
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')
    
    # Generate stats
    total_size = sum(len(json.dumps(doc)) for doc in deduped_docs)
    avg_size = total_size / len(deduped_docs) if deduped_docs else 0
    
    stats = {
        'total_documents': len(deduped_docs),
        'duplicates_removed': duplicates_removed,
        'total_size_bytes': total_size,
        'average_doc_size_bytes': avg_size,
        'sources': source_counts,
        'generated_at': datetime.now().isoformat()
    }
    
    stats_path = output_dir / 'merge_stats.json'
    with open(stats_path, 'w') as f:
        json.dump(stats, f, indent=2)
    
    print("\n" + "="*70)
    print("✓ Merge complete!")
    print("="*70)
    print(f"Output: {output_path}")
    print(f"Stats: {stats_path}")
    print(f"\nTotal documents: {stats['total_documents']}")
    print(f"Total size: {stats['total_size_bytes'] / 1024 / 1024:.1f} MB")
    print(f"Avg doc size: {stats['average_doc_size_bytes'] / 1024:.1f} KB")
    print("\nSource breakdown:")
    for source, count in stats['sources'].items():
        print(f"  - {source}: {count} docs")
    print("="*70)


if __name__ == '__main__':
    main()
