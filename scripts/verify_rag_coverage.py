#!/usr/bin/env python3
"""
Verify RAG coverage across all data sources.
Tests that queries return relevant results from each source category.
"""

import sys
import os
from pathlib import Path

# Suppress logging
os.environ['CUDA_VISIBLE_DEVICES'] = ''

sys.path.insert(0, str(Path(__file__).parent.parent / 'halbert_core'))

import logging
logging.getLogger('halbert').setLevel(logging.WARNING)
logging.getLogger('sentence_transformers').setLevel(logging.WARNING)

from halbert_core.rag import RAGPipeline


def verify_coverage():
    """Test queries across all source categories."""
    
    print("="*70)
    print("RAG COVERAGE VERIFICATION")
    print("="*70)
    
    # Test queries mapped to expected source categories
    test_cases = [
        # (query, expected_keywords_in_result)
        ("How do I create a ZFS pool?", ["zfs", "zpool", "pool"]),
        ("Backup with Borg", ["borg", "backup", "repository"]),
        ("WireGuard VPN setup", ["wireguard", "wg", "interface"]),
        ("systemd timer cron", ["timer", "systemd", "schedule"]),
        ("fail2ban block IP", ["fail2ban", "ban", "jail"]),
        ("Docker container run", ["docker", "container", "run"]),
        ("Kubernetes deployment", ["kubectl", "deployment", "pod"]),
        ("nginx reverse proxy", ["nginx", "proxy", "upstream"]),
        ("PostgreSQL create database", ["postgres", "createdb", "database"]),
        ("git rebase interactive", ["git", "rebase", "-i"]),
        ("Ansible playbook run", ["ansible", "playbook", "play"]),
        ("AWS S3 bucket sync", ["aws", "s3", "sync"]),
        ("NVIDIA CUDA install", ["nvidia", "cuda", "driver"]),
        ("Podman rootless container", ["podman", "container", "rootless"]),
        ("chmod file permissions", ["chmod", "permission", "mode"]),
        ("rsync copy files", ["rsync", "-a", "sync"]),
        ("curl POST request", ["curl", "-X", "POST"]),
        ("grep search pattern", ["grep", "pattern", "search"]),
        ("find files by name", ["find", "-name", "file"]),
        ("tar extract archive", ["tar", "-x", "extract"]),
    ]
    
    print(f"\nLoading knowledge base...")
    
    # Redirect stderr to suppress tqdm
    old_stderr = sys.stderr
    sys.stderr = open('/dev/null', 'w')
    try:
        pipeline = RAGPipeline(
            data_dir=Path('data'),
            use_reranking=True,
            top_k=3
        )
        pipeline.load_and_index_documents()
    finally:
        sys.stderr.close()
        sys.stderr = old_stderr
    
    print(f"✓ Loaded {len(pipeline.retriever._documents)} documents")
    print(f"\nTesting {len(test_cases)} queries...\n")
    
    results = []
    
    for query, expected_keywords in test_cases:
        docs = pipeline.retrieve(query)
        
        # Check if any expected keyword appears in results
        found = False
        found_in = ""
        
        for doc in docs:
            content = f"{doc.get('name', '')} {doc.get('content', '')}".lower()
            for kw in expected_keywords:
                if kw.lower() in content:
                    found = True
                    found_in = doc.get('name', 'Unknown')[:40]
                    break
            if found:
                break
        
        status = "✅" if found else "❌"
        results.append((query, found, found_in))
        
        if found:
            print(f"{status} {query[:40]:<40} → {found_in}")
        else:
            top_result = docs[0]['name'][:40] if docs else "NO RESULTS"
            print(f"{status} {query[:40]:<40} → Got: {top_result}")
    
    # Summary
    passed = sum(1 for _, f, _ in results if f)
    total = len(results)
    pct = (passed / total) * 100
    
    print("\n" + "="*70)
    print(f"RESULTS: {passed}/{total} ({pct:.0f}%) queries returned expected results")
    print("="*70)
    
    if pct < 80:
        print("\n⚠️  Coverage below 80% - investigate failed queries")
    else:
        print("\n✅ Good coverage! RAG is working well.")
    
    return passed, total


if __name__ == '__main__':
    passed, total = verify_coverage()
    sys.exit(0 if passed >= total * 0.8 else 1)
