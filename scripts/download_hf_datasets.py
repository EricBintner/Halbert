#!/usr/bin/env python3
"""
Download HuggingFace datasets and convert to RAG JSONL format.

Downloads:
1. tmskss/linux-man-pages-tldr-summarized (481 examples)
2. harpomaxx/unix-commands (100 examples)
3. Dam-Buty/arch-wiki (12,657 examples)

Converts to unified format:
{
  "name": "command_name",
  "section": "1",
  "description": "brief description",
  "full_text": "complete content",
  "metadata": {
    "source_type": "hf_dataset",
    "dataset": "dataset_name",
    "license": "license_info"
  }
}
"""
import json
from pathlib import Path
from typing import Dict, List

from datasets import load_dataset


def convert_tldr(dataset) -> List[Dict]:
    """Convert tmskss/linux-man-pages-tldr-summarized."""
    docs = []
    for item in dataset:
        # Schema: Command, Text, Summary
        command = item.get('Command', '').strip()
        text = item.get('Text', '').strip()
        summary = item.get('Summary', '').strip()
        
        # Extract section from command like "ls(1)"
        section = ''
        if '(' in command and ')' in command:
            section = command.split('(')[1].split(')')[0]
            name = command.split('(')[0].strip()
        else:
            name = command
        
        # Combine summary and text
        full_text = f"{summary}\n\n{text}" if summary else text
        
        docs.append({
            'name': name,
            'section': section,
            'description': summary[:200] if summary else text[:200],
            'full_text': full_text,
            'metadata': {
                'source_type': 'hf_dataset',
                'dataset': 'tmskss/linux-man-pages-tldr-summarized',
                'license': 'CC BY 4.0',
                'trust': 'community_curated'
            }
        })
    return docs


def convert_unix_commands(dataset) -> List[Dict]:
    """Convert harpomaxx/unix-commands."""
    docs = []
    for item in dataset:
        # Schema: input, instruction, output
        instruction = item.get('instruction', '').strip()
        input_text = item.get('input', '').strip()
        output = item.get('output', '').strip()
        
        # Extract command name from instruction or output
        command = 'unknown'
        if input_text:
            # Try to extract command from input
            words = input_text.split()
            if words:
                command = words[0]
        
        full_text = f"Instruction: {instruction}\n\nInput: {input_text}\n\nOutput: {output}"
        
        docs.append({
            'name': command,
            'section': '',
            'description': instruction[:200],
            'full_text': full_text,
            'metadata': {
                'source_type': 'hf_dataset',
                'dataset': 'harpomaxx/unix-commands',
                'license': 'Apache 2.0',
                'trust': 'community_curated'
            }
        })
    return docs


def convert_arch_wiki(dataset, max_docs: int = 3000) -> List[Dict]:
    """
    Convert Dam-Buty/arch-wiki.
    
    Args:
        dataset: HF dataset
        max_docs: Limit docs (12k is too much, sample 3k diverse)
    """
    docs = []
    
    # Get unique titles first for deduplication
    seen_titles = set()
    
    for i, item in enumerate(dataset):
        if len(docs) >= max_docs:
            break
            
        # Schema: title, section, content
        title = item.get('title', '').strip()
        section = item.get('section', '').strip()
        content = item.get('content', '').strip()
        
        # Skip if we've seen this title
        if title in seen_titles:
            continue
        seen_titles.add(title)
        
        # Skip very short content
        if len(content) < 100:
            continue
        
        # Create a combined title for name
        full_title = f"{title} - {section}" if section else title
        
        docs.append({
            'name': title,
            'section': section,
            'description': content[:200],
            'full_text': content,
            'metadata': {
                'source_type': 'hf_dataset',
                'dataset': 'Dam-Buty/arch-wiki',
                'license': 'GNU FDL',
                'trust': 'vendor_docs',
                'wiki_title': title,
                'wiki_section': section
            }
        })
    
    return docs


def main():
    output_dir = Path('data/linux/hf-datasets')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("="*70)
    print("Downloading HuggingFace datasets for RAG")
    print("="*70)
    
    # 1. TLDR
    print("\n1. Loading tmskss/linux-man-pages-tldr-summarized...")
    try:
        ds1 = load_dataset("tmskss/linux-man-pages-tldr-summarized", split="train")
        print(f"   Loaded {len(ds1)} examples")
        docs1 = convert_tldr(ds1)
        
        out_path = output_dir / 'tldr_man_pages.jsonl'
        with open(out_path, 'w') as f:
            for doc in docs1:
                f.write(json.dumps(doc, ensure_ascii=False) + '\n')
        print(f"   ✓ Wrote {len(docs1)} docs to {out_path}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    
    # 2. Unix Commands
    print("\n2. Loading harpomaxx/unix-commands...")
    try:
        ds2 = load_dataset("harpomaxx/unix-commands", split="train")
        print(f"   Loaded {len(ds2)} examples")
        docs2 = convert_unix_commands(ds2)
        
        out_path = output_dir / 'unix_commands.jsonl'
        with open(out_path, 'w') as f:
            for doc in docs2:
                f.write(json.dumps(doc, ensure_ascii=False) + '\n')
        print(f"   ✓ Wrote {len(docs2)} docs to {out_path}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    
    # 3. Arch Wiki (sample 3000)
    print("\n3. Loading Dam-Buty/arch-wiki (sampling 3000 diverse docs)...")
    try:
        ds3 = load_dataset("Dam-Buty/arch-wiki", split="train")
        print(f"   Loaded {len(ds3)} examples")
        docs3 = convert_arch_wiki(ds3, max_docs=3000)
        
        out_path = output_dir / 'arch_wiki.jsonl'
        with open(out_path, 'w') as f:
            for doc in docs3:
                f.write(json.dumps(doc, ensure_ascii=False) + '\n')
        print(f"   ✓ Wrote {len(docs3)} docs to {out_path}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    
    print("\n" + "="*70)
    print("✓ HuggingFace dataset download complete!")
    print(f"Output directory: {output_dir}")
    print("="*70)


if __name__ == '__main__':
    main()
