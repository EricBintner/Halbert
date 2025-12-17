"""
Documentation Discovery - Automatically find documentation for installed software.

This module goes beyond the static registry to dynamically discover
documentation opportunities by querying the system itself.

Approaches:
1. Package manager metadata (apt, pacman, dnf) - get Homepage URLs
2. Man page detection - identify tools without local docs
3. Well-known documentation patterns - match URLs to doc sites
4. Service config detection - /etc/<service>/ implies documentation exists
"""

import subprocess
import re
import logging
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredDoc:
    """A dynamically discovered documentation source."""
    package_name: str
    doc_url: Optional[str]
    homepage: Optional[str]
    description: str
    has_man_page: bool
    has_local_docs: bool
    discovery_method: str  # 'apt', 'pacman', 'man', 'config'
    confidence: float  # How confident are we this URL is documentation?


# Well-known documentation URL patterns
DOC_URL_PATTERNS = [
    (r'docs\.', 0.95),           # docs.nginx.com
    (r'documentation\.', 0.95),  # documentation.ubuntu.com
    (r'/docs/', 0.9),            # github.com/x/y/docs/
    (r'/doc/', 0.9),             # example.com/doc/
    (r'wiki\.', 0.85),           # wiki.archlinux.org
    (r'man\.', 0.8),             # man.openbsd.org
    (r'readthedocs', 0.95),      # x.readthedocs.io
    (r'gitbook', 0.9),           # x.gitbook.io
    (r'/manual', 0.85),          # php.net/manual
    (r'/guide', 0.8),            # example.com/guide
]


def _run_command(cmd: List[str], timeout: int = 5) -> Tuple[int, str, str]:
    """Run a command safely with timeout."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", f"command not found: {cmd[0]}"


def _score_doc_url(url: str) -> float:
    """Score how likely a URL is to be documentation."""
    if not url:
        return 0.0
    
    url_lower = url.lower()
    
    # Check against patterns
    max_score = 0.5  # Base score for having any URL
    for pattern, score in DOC_URL_PATTERNS:
        if re.search(pattern, url_lower):
            max_score = max(max_score, score)
    
    return max_score


def get_package_docs_apt(package: str) -> Optional[DiscoveredDoc]:
    """Get documentation info from apt (Debian/Ubuntu)."""
    code, stdout, _ = _run_command(['apt-cache', 'show', package])
    if code != 0:
        return None
    
    homepage = None
    description = ""
    
    for line in stdout.splitlines():
        if line.startswith('Homepage:'):
            homepage = line.split(':', 1)[1].strip()
        elif line.startswith('Description:'):
            description = line.split(':', 1)[1].strip()
    
    if not homepage and not description:
        return None
    
    # Check for man page
    has_man = _run_command(['man', '-w', package])[0] == 0
    
    # Check for local docs
    local_docs = Path(f'/usr/share/doc/{package}').exists()
    
    return DiscoveredDoc(
        package_name=package,
        doc_url=homepage if _score_doc_url(homepage) > 0.7 else None,
        homepage=homepage,
        description=description,
        has_man_page=has_man,
        has_local_docs=local_docs,
        discovery_method='apt',
        confidence=_score_doc_url(homepage),
    )


def get_package_docs_pacman(package: str) -> Optional[DiscoveredDoc]:
    """Get documentation info from pacman (Arch Linux)."""
    code, stdout, _ = _run_command(['pacman', '-Qi', package])
    if code != 0:
        return None
    
    url = None
    description = ""
    
    for line in stdout.splitlines():
        if line.startswith('URL'):
            url = line.split(':', 1)[1].strip()
        elif line.startswith('Description'):
            description = line.split(':', 1)[1].strip()
    
    if not url and not description:
        return None
    
    has_man = _run_command(['man', '-w', package])[0] == 0
    local_docs = Path(f'/usr/share/doc/{package}').exists()
    
    return DiscoveredDoc(
        package_name=package,
        doc_url=url if _score_doc_url(url) > 0.7 else None,
        homepage=url,
        description=description,
        has_man_page=has_man,
        has_local_docs=local_docs,
        discovery_method='pacman',
        confidence=_score_doc_url(url),
    )


def get_package_docs(package: str) -> Optional[DiscoveredDoc]:
    """Get documentation info from any available package manager."""
    # Try apt first (Debian/Ubuntu)
    result = get_package_docs_apt(package)
    if result:
        return result
    
    # Try pacman (Arch)
    result = get_package_docs_pacman(package)
    if result:
        return result
    
    # Could add dnf, zypper, etc.
    return None


def check_man_page_exists(command: str) -> bool:
    """Check if a man page exists for a command."""
    code, _, _ = _run_command(['man', '-w', command])
    return code == 0


def check_local_docs_exist(package: str) -> bool:
    """Check if local documentation exists."""
    doc_paths = [
        Path(f'/usr/share/doc/{package}'),
        Path(f'/usr/share/doc/{package}-doc'),
        Path(f'/usr/local/share/doc/{package}'),
    ]
    return any(p.exists() for p in doc_paths)


def analyze_service_for_docs(service_name: str) -> Dict:
    """
    Analyze a service to determine if documentation would be helpful.
    
    Returns a dict with:
    - needs_docs: bool - Do we think this needs documentation?
    - has_local_docs: bool - Are there local docs available?
    - suggested_url: str | None - URL we think has docs
    - confidence: float - How confident are we?
    - reason: str - Why we're suggesting this
    """
    # Strip common suffixes
    clean_name = service_name
    for suffix in ['.service', 'd', '-daemon']:
        if clean_name.endswith(suffix):
            clean_name = clean_name[:-len(suffix)]
            break
    
    result = {
        'service': service_name,
        'package': clean_name,
        'needs_docs': False,
        'has_local_docs': False,
        'has_man_page': False,
        'suggested_url': None,
        'confidence': 0.0,
        'reason': '',
    }
    
    # Check package manager
    pkg_info = get_package_docs(clean_name)
    if pkg_info:
        result['has_local_docs'] = pkg_info.has_local_docs
        result['has_man_page'] = pkg_info.has_man_page
        result['suggested_url'] = pkg_info.doc_url or pkg_info.homepage
        result['confidence'] = pkg_info.confidence
        
        if not pkg_info.has_local_docs and not pkg_info.has_man_page:
            result['needs_docs'] = True
            result['reason'] = f"No local docs or man page for '{clean_name}'"
        elif pkg_info.doc_url:
            result['needs_docs'] = True
            result['reason'] = f"Official docs available at {pkg_info.doc_url}"
    else:
        # No package info - check man page directly
        result['has_man_page'] = check_man_page_exists(clean_name)
        result['has_local_docs'] = check_local_docs_exist(clean_name)
        
        if not result['has_man_page'] and not result['has_local_docs']:
            result['needs_docs'] = True
            result['confidence'] = 0.6
            result['reason'] = f"No local documentation found for '{clean_name}'"
    
    return result


def get_undocumented_services(services: List[str]) -> List[Dict]:
    """
    Analyze a list of services and return those that need documentation.
    
    This is designed to be called with discovered service names.
    """
    needs_docs = []
    
    for service in services:
        analysis = analyze_service_for_docs(service)
        if analysis['needs_docs']:
            needs_docs.append(analysis)
    
    # Sort by confidence (higher = more likely to benefit from docs)
    needs_docs.sort(key=lambda x: x['confidence'], reverse=True)
    
    return needs_docs


# ═══════════════════════════════════════════════════════════════════════════════
# Integration with DocSuggester
# ═══════════════════════════════════════════════════════════════════════════════

def enrich_suggestions_with_discovery(discoveries: List[dict]) -> List[dict]:
    """
    Enrich discovery data with documentation analysis.
    
    For services not in our static registry, try to find docs dynamically.
    """
    enriched = []
    
    for disc in discoveries:
        if disc.get('type') == 'SERVICE':
            service_name = disc.get('name', '')
            analysis = analyze_service_for_docs(service_name)
            
            if analysis['needs_docs'] and analysis['suggested_url']:
                enriched.append({
                    'discovery': disc,
                    'doc_url': analysis['suggested_url'],
                    'confidence': analysis['confidence'],
                    'reason': analysis['reason'],
                    'source': 'dynamic_discovery',
                })
    
    return enriched
