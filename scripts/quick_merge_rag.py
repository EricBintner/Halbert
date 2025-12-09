#!/usr/bin/env python3
"""Quick merge with proper normalization - no hanging."""
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / 'cerebric_core'))
from cerebric_core.rag.pipeline import RAGPipeline

def main():
    print("Quick RAG Merge with Normalization")
    print("="*60)
    
    data_dir = Path('data/linux')
    output_dir = data_dir / 'merged'
    
    # Use RAGPipeline for normalization
    pipeline = RAGPipeline(data_dir=Path('data'))
    
    # Source files - organized by category
    sources = {
        # Original sources
        'vendor_docs': data_dir / 'vendor-docs' / 'vendor_docs_full.jsonl',
        'tldr': data_dir / 'hf-datasets' / 'tldr_man_pages.jsonl',
        'unix_cmds': data_dir / 'hf-datasets' / 'unix_commands.jsonl',
        'arch_wiki': data_dir / 'hf-datasets' / 'arch_wiki.jsonl',
        
        # Containers & Cloud
        'nvidia_docs': data_dir / 'nvidia-docs' / 'nvidia_cuda_docs.jsonl',
        'docker_docs': data_dir / 'docker-docs' / 'docker_docs.jsonl',
        'k8s_docs': data_dir / 'kubernetes-docs' / 'k8s_docs.jsonl',
        
        # Filesystems & Storage
        'filesystem_docs': data_dir / 'filesystem-docs' / 'filesystem_docs.jsonl',
        
        # Backup Tools
        'backup_docs': data_dir / 'backup-docs' / 'backup_docs.jsonl',
        
        # Network Tools
        'network_docs': data_dir / 'network-docs' / 'network_docs.jsonl',
        
        # System & Services
        'systemd_docs': data_dir / 'systemd-docs' / 'systemd_docs.jsonl',
        
        # Security
        'security_docs': data_dir / 'security-docs' / 'security_docs.jsonl',
        
        # GPU (AMD)
        'rocm_docs': data_dir / 'rocm-docs' / 'rocm_docs.jsonl',
        
        # More Containers
        'podman_docs': data_dir / 'podman-docs' / 'podman_docs.jsonl',
        
        # Databases
        'database_docs': data_dir / 'database-docs' / 'database_docs.jsonl',
        
        # Web Servers
        'webserver_docs': data_dir / 'webserver-docs' / 'webserver_docs.jsonl',
        
        # Dev Tools
        'devtools_docs': data_dir / 'devtools-docs' / 'devtools_docs.jsonl',
        
        # Automation/IaC
        'automation_docs': data_dir / 'automation-docs' / 'automation_docs.jsonl',
        
        # Extended Arch Wiki
        'arch_wiki_ext': data_dir / 'arch-wiki-ext' / 'arch_wiki_ext.jsonl',
        
        # Ubuntu Server
        'ubuntu_server': data_dir / 'ubuntu-server' / 'ubuntu_server.jsonl',
        
        # Cloud CLIs
        'aws_cli': data_dir / 'aws-cli' / 'aws_cli.jsonl',
        
        # More K8s/Helm
        'helm_k8s': data_dir / 'helm-k8s' / 'helm_k8s.jsonl',
        
        # More systemd
        'systemd_ext': data_dir / 'systemd-ext' / 'systemd_ext.jsonl',
        
        # Monitoring
        'monitoring_docs': data_dir / 'monitoring-docs' / 'monitoring_docs.jsonl',
        
        # Linux Core (man pages)
        'linux_core': data_dir / 'linux-core-docs' / 'linux-core_docs.jsonl',
        
        # Logging
        'logging_docs': data_dir / 'logging-docs' / 'logging_docs.jsonl',
        
        # SSL/Certs
        'ssl_certs': data_dir / 'ssl-certs-docs' / 'ssl-certs_docs.jsonl',
        
        # Python Tools
        'python_tools': data_dir / 'python-tools-docs' / 'python-tools_docs.jsonl',
        
        # Message Queues
        'message_queues': data_dir / 'message-queues-docs' / 'message-queues_docs.jsonl',
        
        # Caching
        'caching': data_dir / 'caching-docs' / 'caching_docs.jsonl',
        
        # Linux Utils
        'linux_utils': data_dir / 'linux-utils-docs' / 'linux-utils_docs.jsonl',
        
        # More Arch Wiki
        'more_arch': data_dir / 'more-arch' / 'more_arch.jsonl',
        
        # Final Push (more Linux tools)
        'final_push': data_dir / 'final-push' / 'final_push.jsonl',
        
        # 3K Push
        '3k_push': data_dir / '3k-push' / '3k_push.jsonl',
        
        # User-added sources (Phase 10)
        'user_added': data_dir / 'user-sources' / 'user_added.jsonl',
    }
    
    all_docs = []
    
    for name, path in sources.items():
        if not path.exists():
            print(f"⚠ Skipping {name} (not found)")
            continue
        
        print(f"Loading {name}...", end=' ', flush=True)
        docs = pipeline._load_jsonl(path)
        normalized = pipeline._normalize_documents(docs)
        all_docs.extend(normalized)
        print(f"{len(normalized)} docs")
    
    print(f"\nTotal loaded: {len(all_docs)}")
    
    # Dedup by name, preferring docs WITH attribution metadata
    print("Deduplicating...", end=' ', flush=True)
    seen = {}  # key -> doc
    
    for doc in all_docs:
        # Use just name for dedup key (simpler, avoids description variants)
        key = doc.get('name', '')
        
        # Check if doc has full attribution (Phase 10 user-added)
        has_attribution = bool(doc.get('metadata', {}).get('source_url'))
        
        if key not in seen:
            seen[key] = doc
        elif has_attribution:
            # Prefer doc with attribution over one without
            existing_has_attr = bool(seen[key].get('metadata', {}).get('source_url'))
            if not existing_has_attr:
                seen[key] = doc
    
    deduped = list(seen.values())
    
    print(f"{len(deduped)} unique (removed {len(all_docs) - len(deduped)})")
    
    # Save
    output_path = output_dir / 'rag_corpus_merged.jsonl'
    print(f"\nSaving to {output_path}...")
    with open(output_path, 'w') as f:
        for doc in deduped:
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')
    
    print(f"✓ Done! {len(deduped)} documents")
    
    # Quick check for NVIDIA
    nvidia_count = sum(1 for d in deduped if 'nvidia' in d.get('name', '').lower() or 'cuda' in d.get('name', '').lower())
    print(f"  Including {nvidia_count} NVIDIA/CUDA docs")

if __name__ == '__main__':
    main()
